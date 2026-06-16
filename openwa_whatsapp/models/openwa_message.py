import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OpenwaMessage(models.Model):
    _name = 'openwa.message'
    _description = 'WhatsApp Message'
    _order = 'timestamp asc, id asc'

    chat_id = fields.Many2one('openwa.chat', string='Chat', ondelete='cascade', required=True)
    body = fields.Text(string='Message Body')
    type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('document', 'Document'),
    ], string='Message Type', default='text')
    direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Direction', required=True)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    wa_message_id = fields.Char(string='WhatsApp Message ID')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')

    def _to_dict(self):
        self.ensure_one()
        return {
            'id': self.id,
            'chat_id': self.chat_id.id,
            'chat_jid': self.chat_id.jid,
            'body': self.body or '',
            'type': self.type,
            'direction': self.direction,
            'timestamp': fields.Datetime.to_string(self.timestamp) if self.timestamp else '',
            'attachment_url': f'/web/content/{self.attachment_id.id}?download=true' if self.attachment_id else False,
        }

    def _broadcast_message(self, message):
        """Broadcast to the session owner's private bus channel."""
        session = message.chat_id.session_id
        if session and session.user_id:
            channel = f'openwa_channel_{session.user_id.id}'
        else:
            channel = 'openwa_channel'
        self.env['bus.bus']._sendone(channel, 'openwa_message', {
            'type': 'message_received' if message.direction == 'inbound' else 'message_sent',
            'message': message._to_dict(),
        })

    @api.model
    def send_message(self, chat_id, text=None, file_base64=None, filename=None, mimetype=None, file_type=None, image_base64=None):
        chat = self.env['openwa.chat'].browse(chat_id)
        if not chat.exists():
            raise UserError(_("Chat does not exist."))

        # Use the session linked to this chat
        session = chat.session_id
        if not session:
            raise UserError(_("This chat has no linked WhatsApp session."))
        if session.status != 'ready':
            raise UserError(_("Your WhatsApp session is not connected (status: %s). Please start and authenticate your session.") % session.status)

        session_name = session.session_name
        wa_msg_id = None
        b64_data = file_base64 or image_base64
        attachment = False

        if b64_data:
            # Determine if it is an image or document
            is_image = False
            if file_type == 'image' or (mimetype and mimetype.startswith('image/')):
                is_image = True
            elif image_base64 and not file_type:
                is_image = True

            msg_type = 'image' if is_image else 'document'
            payload = {
                'chatId': chat.jid,
                'base64': b64_data,
                'mimetype': mimetype or ('image/png' if is_image else 'application/pdf'),
                'filename': filename or ('image.png' if is_image else 'document.pdf'),
                'caption': text or ''
            }

            endpoint = f'/sessions/{session_name}/messages/send-image' if is_image else f'/sessions/{session_name}/messages/send-document'
            res = self.env['res.config.settings']._openwa_api_request(
                'POST', endpoint, json_data=payload
            )
            if res.status_code not in (200, 201):
                raise UserError(_("Failed to send %s: %s") % (msg_type, res.text))
            wa_msg_id = res.json().get('messageId')

            attachment = self.env['ir.attachment'].create({
                'name': filename or ('image.png' if is_image else 'document.pdf'),
                'type': 'binary',
                'datas': b64_data,
                'res_model': 'openwa.message',
                'public': True,
            })
            body = text or filename or (_('[Image]') if is_image else _('[Document]'))
        else:
            msg_type = 'text'
            body = text or ''
            payload = {'chatId': chat.jid, 'text': body}
            res = self.env['res.config.settings']._openwa_api_request(
                'POST', f'/sessions/{session_name}/messages/send-text', json_data=payload
            )
            if res.status_code not in (200, 201):
                raise UserError(_("Failed to send message: %s") % res.text)
            wa_msg_id = res.json().get('messageId')

        message = self.create({
            'chat_id': chat.id,
            'body': body,
            'type': msg_type,
            'direction': 'outbound',
            'timestamp': fields.Datetime.now(),
            'wa_message_id': wa_msg_id,
            'attachment_id': attachment.id if attachment else False,
        })
        if attachment:
            attachment.write({'res_id': message.id})

        chat.write({'last_message_body': body, 'last_message_date': fields.Datetime.now()})
        self._broadcast_message(message)
        return message._to_dict()

    @api.model
    def get_messages_for_chat(self, chat_id):
        messages = self.search([('chat_id', '=', chat_id)])
        return [msg._to_dict() for msg in messages]
