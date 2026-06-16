import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Global / shared settings ──────────────────────────────────────────────
    openwa_api_url = fields.Char(
        string='OpenWA API URL',
        config_parameter='openwa.api_url',
        default='http://localhost:2785',
        help='Base URL of the self-hosted NestJS OpenWA gateway (e.g. http://localhost:2785)'
    )
    openwa_api_key = fields.Char(
        string='API Key (X-API-Key)',
        config_parameter='openwa.api_key',
        help='Security key sent in X-API-Key header to the NestJS server'
    )
    openwa_webhook_base_url = fields.Char(
        string='Odoo Base URL',
        config_parameter='openwa.webhook_base_url',
        default='http://localhost:8069',
        help='Public base URL of this Odoo instance. OpenWA will POST webhooks to <base_url>/openwa/webhook'
    )
    openwa_dashboard_url = fields.Char(
        string='OpenWA Dashboard URL',
        config_parameter='openwa.dashboard_url',
        default='http://localhost:2886',
        help='URL of the OpenWA web dashboard (e.g. http://localhost:2886)'
    )

    # ── Open Dashboard ────────────────────────────────────────────────────────
    def action_open_openwa_dashboard(self):
        """Open the OpenWA Dashboard in a new browser tab."""
        ICP = self.env['ir.config_parameter'].sudo()
        dashboard_url = ICP.get_param('openwa.dashboard_url', 'http://localhost:2886').rstrip('/')
        return {
            'type': 'ir.actions.act_url',
            'url': dashboard_url,
            'target': 'new',
        }

    # ── Test Connection ───────────────────────────────────────────────────────
    def action_test_openwa_connection(self):
        """Test connectivity to the OpenWA NestJS gateway."""
        try:
            res = self._openwa_api_request('GET', '/sessions')
            if res.status_code == 200:
                data = res.json()
                count = len(data) if isinstance(data, list) else '?'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('✅ OpenWA Connected'),
                        'message': _('Successfully reached the OpenWA server. %s session(s) found.') % count,
                        'type': 'success',
                        'sticky': False,
                    },
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('❌ Connection Failed'),
                        'message': _('OpenWA server responded with HTTP %s: %s') % (res.status_code, res.text[:200]),
                        'type': 'danger',
                        'sticky': True,
                    },
                }
        except UserError as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('❌ Cannot Reach OpenWA'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                },
            }

    # ── Utility: generic HTTP request to the NestJS gateway ──────────────────
    @api.model
    def _openwa_api_request(self, method, path, json_data=None):
        ICP = self.env['ir.config_parameter'].sudo()
        api_url = ICP.get_param('openwa.api_url', 'http://localhost:2785').rstrip('/')
        api_key = ICP.get_param('openwa.api_key', '')

        if not path.startswith('/api/'):
            path = f"/api{path}" if path.startswith('/') else f"/api/{path}"

        url = f"{api_url}{path}"
        headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}

        try:
            import requests
            return requests.request(method, url, headers=headers, json=json_data, timeout=15)
        except Exception as e:
            raise UserError(_("Failed to connect to OpenWA server at %s: %s") % (api_url, e))
