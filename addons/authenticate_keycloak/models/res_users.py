from odoo import fields, models, api
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_keycloak_user = fields.Boolean(
        string='Keycloak User',
        default=False,
        help='User authenticated through Keycloak SSO'
    )

    keycloak_sub = fields.Char(
        string='Keycloak Subject ID',
        help='Unique identifier from Keycloak'
    )

    division = fields.Char(
        string='Division',
        help='Division'
    )
    
    department = fields.Char(
        string='Department',
        help='Department'
    )

    @classmethod
    def authenticate(cls, db, login, password, user_agent_env):
        # Allow None password for Keycloak SSO
        if password is None:
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, 1, {})
                user = env['res.users'].search([
                    ('login', '=', login),
                    ('is_keycloak_user', '=', True),
                    ('active', '=', True)
                ], limit=1)

                if user:
                    return user.id
                else:
                    raise AccessDenied("User not found")

        return super().authenticate(db, login, password, user_agent_env)