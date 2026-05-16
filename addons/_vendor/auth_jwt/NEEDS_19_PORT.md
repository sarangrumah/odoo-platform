# Needs Odoo 19 port

This module was vendored from OCA repository `server-auth` branch **18.0** because
the `19.0` branch did not contain it (or the branch did not exist)
at the time of fetching.

Action required: review for Odoo 19 compatibility (manifest version, ORM API
changes, deprecated fields, security ir.model.access csv format, etc.) and
re-vendor from 19.0 once OCA publishes the port.

Source: https://github.com/OCA/server-auth/tree/18.0/auth_jwt
