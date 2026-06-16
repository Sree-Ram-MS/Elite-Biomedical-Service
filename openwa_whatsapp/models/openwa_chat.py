import re
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OpenwaChat(models.Model):
    _name = 'openwa.chat'
    _description = 'WhatsApp Chat'
    _order = 'last_message_date desc, id desc'

    name = fields.Char(string='Name', required=True)
    jid = fields.Char(string='JID', required=True)
    session_id = fields.Many2one(
        'openwa.session', string='Session', ondelete='set null', index=True
    )
    unread_count = fields.Integer(string='Unread Messages', default=0)
    last_message_body = fields.Text(string='Last Message')
    last_message_date = fields.Datetime(string='Last Message Date', default=fields.Datetime.now)
    profile_pic_url = fields.Char(string='Profile Picture URL')
    message_ids = fields.One2many('openwa.message', 'chat_id', string='Messages')

    _sql_constraints = [
        ('jid_session_unique', 'unique(jid, session_id)', 'JID must be unique per session!'),
    ]

    @api.model
    def get_chat_list(self):
        """Return chats belonging to the current user's session."""
        session = self.env['openwa.session'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not session:
            return []
        chats = self.search([('session_id', '=', session.id)])
        return [self._chat_to_dict(c) for c in chats]

    def _chat_to_dict(self, chat):
        return {
            'id': chat.id,
            'name': chat.name,
            'jid': chat.jid,
            'unread_count': chat.unread_count,
            'last_message_body': chat.last_message_body or '',
            'last_message_date': fields.Datetime.to_string(chat.last_message_date) if chat.last_message_date else '',
            'profile_pic_url': chat.profile_pic_url or '',
        }

    @api.model
    def search_and_add_chat(self, number):
        """Find or create a chat for the given phone number, using the current user's session."""
        cleaned_number = re.sub(r'\D', '', number)
        if not cleaned_number:
            raise UserError(_("Invalid phone number format."))

        # Get the current user's session
        session = self.env['openwa.session'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not session or session.status != 'ready':
            raise UserError(_("Your WhatsApp session is not connected. Please start and authenticate your session first."))

        session_name = session.session_name
        jid = f"{cleaned_number}@c.us"

        # Check if chat already exists for this session
        existing = self.search([('jid', '=', jid), ('session_id', '=', session.id)], limit=1)
        if existing:
            return self._chat_to_dict(existing)

        # Verify number on WhatsApp
        whatsapp_id = jid
        try:
            res = self.env['res.config.settings']._openwa_api_request(
                'GET', f'/sessions/{session_name}/contacts/check/{cleaned_number}'
            )
            if res.status_code == 200:
                data = res.json()
                if not data.get('exists'):
                    raise UserError(_("The phone number %s is not registered on WhatsApp.") % number)
                whatsapp_id = data.get('whatsappId', jid)
            else:
                _logger.warning("Contact check returned %s, using default JID.", res.status_code)
        except UserError as ue:
            raise ue
        except Exception as e:
            _logger.warning("Failed to verify contact %s: %s. Using default JID.", number, e)

        # Fetch contact name and profile pic
        name = number
        profile_pic = ''
        try:
            contact_res = self.env['res.config.settings']._openwa_api_request(
                'GET', f'/sessions/{session_name}/contacts/{whatsapp_id}'
            )
            if contact_res.status_code == 200:
                c_data = contact_res.json()
                name = c_data.get('name') or c_data.get('pushname') or c_data.get('number') or number

            pic_res = self.env['res.config.settings']._openwa_api_request(
                'GET', f'/sessions/{session_name}/contacts/{whatsapp_id}/profile-picture'
            )
            if pic_res.status_code == 200:
                profile_pic = pic_res.json().get('url', '')
        except Exception as e:
            _logger.warning("Could not fetch name/picture for %s: %s", whatsapp_id, e)

        new_chat = self.create({
            'name': name,
            'jid': whatsapp_id,
            'session_id': session.id,
            'unread_count': 0,
            'last_message_body': _('Chat created'),
            'last_message_date': fields.Datetime.now(),
            'profile_pic_url': profile_pic,
        })
        return self._chat_to_dict(new_chat)
