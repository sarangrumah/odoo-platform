# -*- coding: utf-8 -*-
import base64
import functools
import json
import logging
import os

import werkzeug.urls
import werkzeug.utils
from werkzeug.exceptions import BadRequest

from odoo import api, http, SUPERUSER_ID, _, tools, fields
from odoo.exceptions import AccessDenied
from odoo.http import request, Response
from odoo import registry as registry_get
from odoo.tools.misc import clean_context

from odoo.addons.auth_signup.controllers.main import AuthSignupHome as Home
from odoo.addons.web.controllers.utils import ensure_db, _get_login_redirect_url
import string
import random
import requests
import hashlib
import secrets

_logger = logging.getLogger(__name__)


# ----------------------------------------------------------
# helpers
# ----------------------------------------------------------
def fragment_to_query_string(func):
    @functools.wraps(func)
    def wrapper(self, *a, **kw):
        kw.pop('debug', False)
        if not kw:
            return Response("""<html><head><script>
                var l = window.location;
                var q = l.hash.substring(1);
                var r = l.pathname + l.search;
                if(q.length !== 0) {
                    var s = l.search ? (l.search === '?' ? '' : '&') : '?';
                    r = l.pathname + l.search + s + q;
                }
                if (r == l.pathname) {
                    r = '/';
                }
                window.location = r;
            </script></head><body></body></html>""")
        return func(self, *a, **kw)

    return wrapper


# ----------------------------------------------------------
# Controller
# ----------------------------------------------------------
class AuthenticateKeycloakLogin(Home):
    def get_keycloak_url(self, is_active):
        if is_active:
            # return_url = request.httprequest.url_root + 'authenticate/keycloak'
            return_url = os.environ.get("KEYCLOAK_REDIRECT_URI", "")
            client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "")
            realm = os.environ.get("KEYCLOAK_REALM", "")
            auth_url = os.environ.get("KEYCLOAK_BASE_URL", "") + "/realms/" + realm + "/protocol/openid-connect/auth"
            state = self.get_state()
            params = dict(
                response_type='code',
                client_id=client_id,
                redirect_uri=return_url,
                scope='openid',
                state=json.dumps(state),
            )
            return "%s?%s" % (auth_url, werkzeug.urls.url_encode(params))
        else:
            return ""

    def get_state(self):
        redirect = request.params.get('redirect') or 'web'
        if not redirect.startswith(('//', 'http://', 'https://')):
            redirect = '%s%s' % (request.httprequest.url_root, redirect[1:] if redirect[0] == '/' else redirect)
        state = dict(
            d=request.session.db,
            r=werkzeug.urls.url_quote_plus(redirect),
            m=''.join(random.choices(string.ascii_uppercase + string.digits, k=40))
        )
        token = request.params.get('token')
        if token:
            state['t'] = token
        return state

    @http.route()
    def web_login(self, *args, **kw):
        auth_with_keycloak = request.env['ir.config_parameter'].sudo().get_param('authenticate_keycloak.is_active')
        ensure_db()
        if request.httprequest.method == 'GET' and request.session.uid and request.params.get('redirect'):
            return request.redirect(request.params.get('redirect'))

        response = super(AuthenticateKeycloakLogin, self).web_login(*args, **kw)
        if response.is_qweb:
            error = request.params.get('oauth_error')
            if error == '1':
                error = _("Sign up is not allowed on this database.")
            elif error == '2':
                error = _("Access Denied")
            elif error == '3':
                error = _(
                    "You do not have access to this database or your invitation has expired. Please ask for an invitation and be sure to follow the link in your invitation email.")
            else:
                error = None

            response.qcontext['keycloak_is_active'] = auth_with_keycloak
            response.qcontext['keycloak_url'] = self.get_keycloak_url(auth_with_keycloak)
            response.qcontext['keycloak_css_class'] = request.env['ir.config_parameter'].sudo().get_param(
                'authenticate_keycloak.css_class')
            response.qcontext['keycloak_button_label'] = request.env['ir.config_parameter'].sudo().get_param(
                'authenticate_keycloak.button_label')
            if error:
                response.qcontext['error'] = error

        return response


class AuthenticateKeycloakController(http.Controller):

    @http.route('/authenticate/keycloak', type='http', auth='none')
    @fragment_to_query_string
    def signin(self, **kw):
        state = json.loads(kw['state'])
        dbname = state['d']
        if not http.db_filter([dbname]):
            return BadRequest()
        ensure_db(db=dbname)

        request.update_context(**clean_context(state.get('c', {})))
        try:
            code = kw.get('code')
            if not code:
                return request.redirect('/web/login')

            # Keycloak configuration
            client_id = os.environ.get('KEYCLOAK_CLIENT_ID', '')
            client_secret = os.environ.get('KEYCLOAK_CLIENT_SECRET', '')
            base_url = os.environ.get('KEYCLOAK_BASE_URL', '')
            # redirect_uri = request.httprequest.base_url
            redirect_uri = os.environ.get('KEYCLOAK_REDIRECT_URI', '')
            realm = os.environ.get('KEYCLOAK_REALM', '')
            token_url = base_url + '/realms/' + realm + '/protocol/openid-connect/token'
            userinfo_url = base_url + '/realms/' + realm + '/protocol/openid-connect/userinfo'

            # Exchange code for token
            token_data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri, 'client_id': client_id, 'client_secret': client_secret}
            token_resp = requests.post(token_url, data=token_data)
            if token_resp.status_code != 200:
                return request.redirect('/web/login?error=token')
            tokens = token_resp.json()
            access_token = tokens.get('access_token')

            # Fetch user info
            headers = {'Authorization': f'Bearer {access_token}'}
            userinfo_resp = requests.get(userinfo_url, headers=headers)
            if userinfo_resp.status_code != 200:
                return request.redirect('/web/login?error=userinfo')
            userinfo = userinfo_resp.json()
            _logger.info(f"Keycloak userinfo: {userinfo}")
            
            email = userinfo.get('email')
            name = userinfo.get('name') or userinfo.get('preferred_username')
            if not email:
                return request.redirect('/web/login?error=noemail')

            # Find user in Odoo
            user = request.env['res.users'].sudo().search([('login', '=', email)], limit=1)
            if not user:
                return request.redirect('/web/login?error=email-not-registered')

            # --- START SYNC LOGIC ---
            # Find or create department from Keycloak userinfo
            department_id = False
            department_name = userinfo.get('dept')
            if department_name:
                department = request.env['hr.department'].sudo().search([('name', 'ilike', department_name)], limit=1)
                if not department:
                    _logger.info(f"Department '{department_name}' from Keycloak not found. Creating it.")
                    department = request.env['hr.department'].sudo().create({'name': department_name})
                department_id = department.id

            # Sync employee data
            if user.employee_id:
                # If employee is already linked, update NIK and department if empty
                employee_to_update = user.employee_id
                _logger.info(f"User {user.login} is linked to employee {employee_to_update.name}. Checking for updates.")
                update_vals = {}
                if not employee_to_update.nik and userinfo.get('nik'):
                    update_vals['nik'] = userinfo.get('nik')
                if not employee_to_update.department_id and department_id:
                    update_vals['department_id'] = department_id
                
                if update_vals:
                    try:
                        employee_to_update.sudo().write(update_vals)
                        _logger.info(f"Successfully updated employee of user {user.login}: {update_vals}")
                    except Exception as e:
                        _logger.error(f"Failed to update linked employee for user {user.login}: {str(e)}")

                self._sync_employee_data_if_needed(employee_to_update)

            else:
                # If not linked, search for an existing employee by email
                _logger.info(f"User {user.login} is not linked to an employee. Searching for existing employee with email {user.login}.")
                employee = request.env['hr.employee'].sudo().search([('work_email', '=', user.login)], limit=1)
                
                if employee:
                    # Employee found, link it and conditionally update NIK and department
                    _logger.info(f"Found existing employee '{employee.name}' (ID: {employee.id}). Linking to user and updating.")
                    
                    update_vals = {'user_id': user.id}
                    if not employee.nik and userinfo.get('nik'):
                        update_vals['nik'] = userinfo.get('nik')
                    if not employee.department_id and department_id:
                        update_vals['department_id'] = department_id

                    try:
                        employee.sudo().write(update_vals)
                        _logger.info(f"Successfully linked and updated employee for user {user.login}.")
                    except Exception as e:
                        _logger.error(f"Failed to update and link existing employee for user {user.login}: {str(e)}")
                    
                    self._sync_employee_data_if_needed(employee)
                else:
                    # Employee not found, do nothing.
                    _logger.warning(f"No existing employee found with email {user.login}. User will not be linked to an employee record.")
            # --- END SYNC LOGIC ---

            # Authenticate and redirect
            request.session.authenticate(request.session.db, user.login, None)
            user.sudo().write({'login_date': fields.Datetime.now()})
            
            redirect = werkzeug.urls.url_unquote_plus(state.get('r') or '') or '/web'
            return request.redirect(redirect)

        except Exception as e:
            _logger.error(f"Keycloak callback error: {str(e)}")
            url = "/web/login?oauth_error=2"
            return request.redirect(url)

    def _sync_employee_data_if_needed(self, employee):
        """Trigger API sync if employee has NIK and some fields are missing."""
        if employee.nik:
            if not all([employee.department_id, employee.job_id, employee.parent_id]):
                _logger.info(f"Employee {employee.name} (NIK: {employee.nik}) is missing some data. Triggering API sync.")
                self._sync_employee_data_from_api(employee)
        else:
            _logger.info(f"Employee {employee.name} has no NIK. Skipping API sync.")

    def _sync_employee_data_from_api(self, employee):
        """Fetch employee details from HC API and update empty fields."""
        try:
            config_params = request.env['ir.config_parameter'].sudo()
            base_url = config_params.get_param('hc.base_url')
            api_key = config_params.get_param('hc.api_key')

            if not base_url or not api_key:
                _logger.warning("Employee Sync: System parameters 'hc.base_url' or 'hc.api_key' are not configured.")
                return

            nik = employee.nik
            endpoint = f"{base_url}api/v1/open-api/employees/{nik}"
            headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}

            _logger.info(f"Employee Sync: Getting data for NIK {nik} from {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=10)
            response.raise_for_status()

            response_data = response.json()
            if not response_data.get('status'):
                _logger.error(f"Employee Sync API Error for NIK {nik}: {response_data.get('message', 'Unknown error')}")
                return

            employee_data = response_data.get('data', {})
            update_vals = {}

            # Sync Department if empty
            department_name = employee_data.get('department')
            if department_name and not employee.department_id:
                department = request.env['hr.department'].sudo().search([('name', 'ilike', department_name)], limit=1)
                if not department:
                    department = request.env['hr.department'].sudo().create({'name': department_name})
                update_vals['department_id'] = department.id

            # Sync Job Title if empty
            job_title = employee_data.get('job_title')
            if job_title and not employee.job_id:
                job = request.env['hr.job'].sudo().search([('name', 'ilike', job_title)], limit=1)
                if not job:
                    job = request.env['hr.job'].sudo().create({'name': job_title})
                update_vals['job_id'] = job.id

            # Sync Superior if empty
            superior_data = employee_data.get('superior')
            if superior_data and superior_data.get('email') and not employee.parent_id:
                superior_email = superior_data.get('email')
                superior_employee = request.env['hr.employee'].sudo().search([('work_email', '=', superior_email)], limit=1)
                if superior_employee and superior_employee.id != employee.id:
                    update_vals['parent_id'] = superior_employee.id
                else:
                    _logger.warning(f"Employee Sync: Superior with email '{superior_email}' not found or is self for NIK {nik}.")

            if update_vals:
                employee.sudo().write(update_vals)
                _logger.info(f"Employee Sync: Successfully synced data for employee {employee.name}: {update_vals}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Employee Sync: API request failed for NIK {employee.nik}: {e}")
        except Exception as e:
            _logger.error(f"Employee Sync: An unexpected error occurred for NIK {employee.nik}: {e}")

    # This helper function is no longer called from signin, but can be kept for other purposes or removed.
    def _update_user_details_from_keycloak(self, user, user_info):
        """Update existing user's employee details with latest info from Keycloak"""
        if not user.employee_id:
            return
        try:
            update_vals = {}
            if user_info.get('nik'):
                update_vals['nik'] = user_info.get('nik')
            
            department_name = user_info.get('dept')
            if department_name:
                department = request.env['hr.department'].sudo().search([('name', 'ilike', department_name)], limit=1)
                if not department:
                    department = request.env['hr.department'].sudo().create({'name': department_name})
                update_vals['department_id'] = department.id

            if update_vals:
                user.employee_id.sudo().write(update_vals)
        except Exception as e:
            _logger.error(f"Failed to update employee details from Keycloak for user {user.login}: {str(e)}")

    def _generate_session(self, sid, user):
        return hashlib.sha256(f"{user.id}-{sid}-{user.keycloak_sub}".encode()).hexdigest()

    def _generate_password(length=12):
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(characters) for _ in range(length))
