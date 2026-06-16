import re
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── NestJS status → Odoo selection value ──────────────────────────────────────
_STATUS_MAP = {
    # uppercase variants (NestJS default)
    'INITIALIZING': 'initializing',
    'STARTING': 'initializing',
    'LAUNCHED': 'initializing',
    'QR': 'qr_ready',
    'QR_READY': 'qr_ready',
    'SCAN_QR_CODE': 'qr_ready',
    'GOT_QR': 'qr_ready',
    'AUTHENTICATING': 'authenticating',
    'AUTHENTICATED': 'authenticating',
    'READY': 'ready',
    'CONNECTED': 'ready',
    'WORKING': 'ready',
    'DISCONNECTED': 'disconnected',
    'STOPPED': 'disconnected',
    'FAILED': 'failed',
    'CRASH': 'failed',
    # lowercase passthrough (in case server already returns lowercase)
    'initializing': 'initializing',
    'qr_ready': 'qr_ready',
    'authenticating': 'authenticating',
    'ready': 'ready',
    'disconnected': 'disconnected',
    'not_created': 'not_created',
    'failed': 'failed',
}


def _slugify_login(login):
    """Convert a user login/name to a valid OpenWA session name (a-z0-9 and hyphens only)."""
    slug = re.sub(r'[^a-z0-9]+', '-', login.lower().strip())
    slug = slug.strip('-')
    return slug or None


class OpenwaSession(models.Model):
    _name = 'openwa.session'
    _description = 'OpenWA WhatsApp User Session'
    _order = 'id desc'

    user_id = fields.Many2one(
        'res.users', string='User', required=True,
        default=lambda self: self.env.user, ondelete='cascade', index=True
    )
    session_name = fields.Char(string='Session Name', required=True, index=True)
    session_uuid = fields.Char(string='Session UUID')
    status = fields.Selection([
        ('not_created', 'Not Created'),
        ('disconnected', 'Disconnected'),
        ('initializing', 'Initializing'),
        ('qr_ready', 'QR Ready'),
        ('authenticating', 'Authenticating'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ], string='Status', default='not_created')
    phone = fields.Char(string='Phone Number')
    push_name = fields.Char(string='WhatsApp Display Name')
    qr_code = fields.Text(string='QR Code')

    _sql_constraints = [
        ('user_unique', 'unique(user_id)', 'Each user can only have one WhatsApp session!'),
        ('session_name_unique', 'unique(session_name)', 'Session name must be unique!'),
    ]

    # ─── JS-callable @api.model methods ───────────────────────────────────────

    @api.model
    def get_my_session_info(self):
        """Return the current user's session info dict (for JS polling)."""
        session = self.search([('user_id', '=', self.env.uid)], limit=1)
        if not session:
            return {'has_session': False, 'status': 'not_created',
                    'session_name': '', 'phone': '', 'push_name': '', 'qr_code': False}
        return session._to_dict()

    @api.model
    def action_create_my_session(self):
        """Create a new session record for the logged-in user."""
        existing = self.search([('user_id', '=', self.env.uid)], limit=1)
        if existing:
            return existing._to_dict()

        # Build session name from user login (letters/numbers/hyphens only)
        user = self.env.user
        base_slug = _slugify_login(user.login)
        if not base_slug:
            base_slug = _slugify_login(user.name or '')
        if not base_slug:
            base_slug = f'wa-{self.env.uid}'

        session_name = base_slug
        # If the slug is already taken, append uid to disambiguate
        if self.search([('session_name', '=', session_name)], limit=1):
            session_name = f'{base_slug}-{self.env.uid}'

        session = self.create({
            'user_id': self.env.uid,
            'session_name': session_name,
            'status': 'not_created',
        })
        return session._to_dict()

    @api.model
    def action_start_my_session(self):
        """Start (or restart) the current user's session on the NestJS gateway."""
        session = self._get_my_session()
        session._do_start()
        return session._to_dict()

    @api.model
    def action_stop_my_session(self):
        """Stop the current user's WhatsApp session."""
        session = self._get_my_session()
        res = self.env['res.config.settings']._openwa_api_request(
            'POST', f'/sessions/{session.session_name}/stop'
        )
        if res.status_code not in (200, 201):
            raise UserError(_("Failed to stop session: %s") % res.text)
        session.write({'status': 'disconnected', 'qr_code': False})
        return session._to_dict()

    @api.model
    def action_delete_my_session(self):
        """Delete / wipe the current user's session from the gateway."""
        session = self._get_my_session()
        res = self.env['res.config.settings']._openwa_api_request(
            'DELETE', f'/sessions/{session.session_name}'
        )
        if res.status_code not in (200, 201, 204, 404):
            raise UserError(_("Failed to delete session: %s") % res.text)
        session.write({
            'status': 'not_created',
            'session_uuid': False,
            'phone': False,
            'push_name': False,
            'qr_code': False,
        })
        return session._to_dict()

    @api.model
    def refresh_my_status(self):
        """Poll NestJS for latest status + QR code and persist changes."""
        session = self.search([('user_id', '=', self.env.uid)], limit=1)
        if not session:
            return {'has_session': False, 'status': 'not_created'}
        session._do_refresh()
        return session._to_dict()

    # ─── Instance helpers ──────────────────────────────────────────────────────

    def _to_dict(self):
        self.ensure_one()
        return {
            'has_session': True,
            'id': self.id,
            'status': self.status,
            'session_name': self.session_name,
            'phone': self.phone or '',
            'push_name': self.push_name or '',
            'qr_code': self.qr_code or False,
        }

    def _get_my_session(self):
        session = self.search([('user_id', '=', self.env.uid)], limit=1)
        if not session:
            raise UserError(_("No WhatsApp session found. Please create one first."))
        return session

    def _normalize_status(self, raw_status):
        """Map NestJS status string (any case/format) to Odoo selection value."""
        if not raw_status:
            return None
        normalized = _STATUS_MAP.get(str(raw_status).strip())
        if not normalized:
            # last-ditch: try lowercase
            normalized = _STATUS_MAP.get(str(raw_status).strip().lower())
        if not normalized:
            _logger.warning("Unknown NestJS status '%s', defaulting to 'initializing'", raw_status)
            normalized = 'initializing'
        return normalized

    def _do_start(self):
        """Launch the Puppeteer engine on NestJS for this session."""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        webhook_base = ICP.get_param('openwa.webhook_base_url', 'http://localhost:8069')

        # ── 1. Fetch existing sessions from NestJS ─────────────────────────────
        res = self.env['res.config.settings']._openwa_api_request('GET', '/sessions')
        if res.status_code != 200:
            raise UserError(_("Cannot reach OpenWA server. Check API URL in Settings.\n\nResponse: %s") % res.text)

        sessions = res.json()
        if isinstance(sessions, dict):
            sessions = sessions.get('data', sessions.get('sessions', []))

        target = next((s for s in sessions if s.get('name') == self.session_name), None)
        uuid = self.session_uuid

        if target:
            uuid = target.get('id', uuid)
            _logger.info("Session '%s' already exists on NestJS (id=%s)", self.session_name, uuid)
        else:
            # ── 2. Create session on NestJS ────────────────────────────────────
            cr = self.env['res.config.settings']._openwa_api_request(
                'POST', '/sessions', json_data={'name': self.session_name}
            )
            if cr.status_code in (200, 201):
                cr_data = cr.json()
                if isinstance(cr_data, dict):
                    uuid = cr_data.get('id', cr_data.get('sessionId', uuid))
                _logger.info("Session '%s' created on NestJS (id=%s)", self.session_name, uuid)
            elif cr.status_code == 409:
                _logger.info("Session '%s' already exists on NestJS (409), continuing.", self.session_name)
            else:
                raise UserError(
                    _("Failed to create session '%s' on server: %s") % (self.session_name, cr.text)
                )

        if uuid and uuid != self.session_uuid:
            self.session_uuid = uuid

        # ── 3. Start the engine ────────────────────────────────────────────────
        sr = self.env['res.config.settings']._openwa_api_request(
            'POST', f'/sessions/{self.session_name}/start'
        )
        if sr.status_code in (200, 201):
            _logger.info("Session '%s' start command accepted.", self.session_name)
        elif sr.status_code == 400:
            # 400 means "Session is already started" — that's fine, just sync status
            _logger.info("Session '%s' already started (400), syncing status from NestJS.", self.session_name)
        else:
            raise UserError(_("Failed to start session: %s") % sr.text)

        # ── 4. Immediately sync real status from NestJS ────────────────────────
        # Don't blindly write 'initializing' — pull the real current state
        self._do_refresh()

        # ── 5. Register Odoo webhook ───────────────────────────────────────────
        webhook_url = webhook_base.rstrip('/') + '/openwa/webhook'
        self._register_webhook(webhook_url)

    def _do_refresh(self):
        """Poll NestJS and update status, phone, push_name, qr_code."""
        self.ensure_one()
        try:
            res = self.env['res.config.settings']._openwa_api_request(
                'GET', f'/sessions/{self.session_name}'
            )
            if res.status_code == 200:
                data = res.json()
                # NestJS may nest the session under a key
                if isinstance(data, dict) and 'session' in data:
                    data = data['session']

                raw_status = data.get('status') or data.get('state') or data.get('engineState')
                odoo_status = self._normalize_status(raw_status)
                if not odoo_status:
                    return

                vals = {'status': odoo_status}

                if odoo_status == 'ready':
                    vals['phone'] = (
                        data.get('phone') or data.get('phoneNumber') or self.phone or ''
                    )
                    vals['push_name'] = (
                        data.get('pushName') or data.get('push_name') or self.push_name or ''
                    )
                    vals['qr_code'] = False

                elif odoo_status == 'qr_ready':
                    # Try to fetch QR directly
                    qr_res = self.env['res.config.settings']._openwa_api_request(
                        'GET', f'/sessions/{self.session_name}/qr'
                    )
                    if qr_res.status_code == 200:
                        qr_data = qr_res.json()
                        vals['qr_code'] = (
                            qr_data.get('qrCode') or qr_data.get('qr') or
                            qr_data.get('data') or False
                        )
                    else:
                        # QR might be embedded in the session data itself
                        vals['qr_code'] = (
                            data.get('qrCode') or data.get('qr') or False
                        )

                else:
                    vals['qr_code'] = False

                self.write(vals)
                _logger.debug("Session '%s' refreshed: %s → %s", self.session_name, raw_status, odoo_status)

            elif res.status_code == 404:
                self.write({'status': 'not_created', 'qr_code': False})
            else:
                _logger.warning("refresh_status for '%s': unexpected %s", self.session_name, res.status_code)

        except Exception as e:
            _logger.warning("refresh_status for '%s' failed: %s", self.session_name, e)

    def _register_webhook(self, webhook_url):
        """Register webhook on NestJS (idempotent)."""
        if not webhook_url:
            return
        try:
            res = self.env['res.config.settings']._openwa_api_request(
                'GET', f'/sessions/{self.session_name}/webhooks'
            )
            if res.status_code == 200:
                existing = res.json()
                if isinstance(existing, list) and any(w.get('url') == webhook_url for w in existing):
                    _logger.info("Webhook already registered for '%s'", self.session_name)
                    return
            payload = {
                'url': webhook_url,
                'events': ['message.received'],
                'secret': 'odoo_openwa_secret',
            }
            self.env['res.config.settings']._openwa_api_request(
                'POST', f'/sessions/{self.session_name}/webhooks', json_data=payload
            )
        except Exception as e:
            _logger.warning("Webhook registration failed for '%s': %s", self.session_name, e)
