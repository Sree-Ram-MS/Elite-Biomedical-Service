import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OpenwaConnectionWizard(models.TransientModel):
    _name = 'openwa.connection.wizard'
    _description = 'OpenWA Connection Pairing Wizard'

    session_name = fields.Char(string='Session Name', required=True)
    status = fields.Char(string='Status')
    qr_code_html = fields.Html(string='QR Code')
    message = fields.Text(string='Message')

    def _update_from_server(self):
        self.ensure_one()
        status = self.status
        session_name = self.session_name

        # Poll session status from NestJS server
        try:
            res = self.env['res.config.settings']._openwa_api_request('GET', f'/sessions/{session_name}')
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict) and 'session' in data:
                    data = data['session']
                status = data.get('status', status) or data.get('state') or data.get('engineState')
                self.status = status
        except Exception as e:
            _logger.error("Failed to fetch session status: %s", str(e))
            self.message = _("Could not communicate with NestJS server: %s") % str(e)
            return

        if status == 'ready':
            self.message = _("WhatsApp session is connected and ready to use!")
            self.qr_code_html = False
            # Register webhooks just in case
            session = self.env['openwa.session'].search([('session_name', '=', session_name)], limit=1)
            if session:
                ICP = self.env['ir.config_parameter'].sudo()
                webhook_base = ICP.get_param('openwa.webhook_base_url', 'http://localhost:8069')
                webhook_url = webhook_base.rstrip('/') + '/openwa/webhook'
                session._register_webhook(webhook_url)
        elif status == 'qr_ready':
            self.message = _("Please scan the QR code using WhatsApp on your mobile device to link Odoo.")
            try:
                qr_res = self.env['res.config.settings']._openwa_api_request('GET', f'/sessions/{session_name}/qr')
                if qr_res.status_code == 200:
                    qr_data = qr_res.json()
                    qr_code = qr_data.get('qrCode') or qr_data.get('qr') or qr_data.get('data')
                    if qr_code:
                        self.qr_code_html = f"""
                            <div style="text-align: center; margin: 15px 0;">
                                <img src="{qr_code}" style="max-width: 260px; border: 3px solid #00a884; padding: 12px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"/>
                                <div style="margin-top: 10px; color: #555; font-size: 13px;">
                                    <strong>Status:</strong> QR Code Ready
                                </div>
                            </div>
                        """
                    else:
                        self.qr_code_html = False
                        self.message = _("QR Code is generating, please wait and click Refresh.")
                else:
                    self.qr_code_html = False
                    self.message = _("QR Code is not ready yet. Please wait a few seconds and click Refresh.")
            except Exception as e:
                self.qr_code_html = False
                self.message = _("Failed to retrieve QR code: %s") % str(e)
        elif status in ('initializing', 'authenticating'):
            self.message = _("Session is initializing or authenticating. Please wait and click Refresh.")
            self.qr_code_html = False
        elif status == 'failed':
            self.message = _("WhatsApp session failed to start. Check NestJS server logs.")
            self.qr_code_html = False
        else:
            self.message = _("WhatsApp session is disconnected. Click Refresh to attempt starting it.")
            self.qr_code_html = False

    def action_refresh(self):
        self.ensure_one()
        session_name = self.session_name

        # If disconnected/created/failed, try starting it
        if self.status in ('disconnected', 'created', 'failed'):
            try:
                self.env['res.config.settings']._openwa_api_request('POST', f'/sessions/{session_name}/start')
                self.status = 'initializing'
            except Exception as e:
                _logger.error("Failed to start session: %s", str(e))

        self._update_from_server()

        # Re-open the same wizard
        return {
            'name': _('WhatsApp Pairing Status'),
            'type': 'ir.actions.act_window',
            'res_model': 'openwa.connection.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
