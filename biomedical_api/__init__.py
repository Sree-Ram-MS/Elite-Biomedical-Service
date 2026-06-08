import odoo.http
# Set session lifetime to 7 days (7 * 24 * 60 * 60 seconds)
odoo.http.SESSION_LIFETIME = 7 * 24 * 60 * 60

from . import controllers
