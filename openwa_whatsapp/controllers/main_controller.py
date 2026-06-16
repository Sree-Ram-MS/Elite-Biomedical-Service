import json
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class OpenwaWebhookController(http.Controller):

    @http.route('/openwa/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def openwa_webhook(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
        except Exception as e:
            _logger.error("Failed to parse webhook JSON: %s", e)
            return request.make_response(
                json.dumps({'error': 'Invalid JSON'}),
                headers=[('Content-Type', 'application/json')], status=400
            )

        event = data.get('event')
        session_name = data.get('sessionId')  # NestJS sends the session name here

        if not session_name:
            return request.make_response(
                json.dumps({'status': 'no_session_id'}),
                headers=[('Content-Type', 'application/json')]
            )

        # Route to the correct openwa.session record
        OpenwaSession = request.env['openwa.session'].sudo()
        session = OpenwaSession.search([('session_name', '=', session_name)], limit=1)
        if not session:
            _logger.info("Webhook for unknown session '%s'. Ignoring.", session_name)
            return request.make_response(
                json.dumps({'status': 'unknown_session'}),
                headers=[('Content-Type', 'application/json')]
            )

        if event == 'message.received':
            return self._handle_message(data, session)

        return request.make_response(
            json.dumps({'status': 'unsupported_event'}),
            headers=[('Content-Type', 'application/json')]
        )

    def _handle_message(self, data, session):
        msg_data = data.get('data', {})
        wa_message_id = msg_data.get('id')

        if not wa_message_id:
            return request.make_response(
                json.dumps({'error': 'Missing message ID'}),
                headers=[('Content-Type', 'application/json')], status=400
            )

        # Avoid duplicates
        OpenwaMsg = request.env['openwa.message'].sudo()
        if OpenwaMsg.search([('wa_message_id', '=', wa_message_id)], limit=1):
            return request.make_response(
                json.dumps({'status': 'duplicate'}),
                headers=[('Content-Type', 'application/json')]
            )

        from_me = msg_data.get('fromMe', False)
        chat_jid = msg_data.get('to') if from_me else msg_data.get('from')

        if not chat_jid:
            return request.make_response(
                json.dumps({'status': 'no_chat_jid'}),
                headers=[('Content-Type', 'application/json')]
            )

        # Find or create chat scoped to this session
        OpenwaChat = request.env['openwa.chat'].sudo()
        chat = OpenwaChat.search([('jid', '=', chat_jid), ('session_id', '=', session.id)], limit=1)
        if not chat:
            name = chat_jid.split('@')[0]
            profile_pic = ''
            try:
                settings_model = request.env['res.config.settings'].sudo()
                contact_res = settings_model._openwa_api_request(
                    'GET', f'/sessions/{session.session_name}/contacts/{chat_jid}'
                )
                if contact_res.status_code == 200:
                    c_data = contact_res.json()
                    name = c_data.get('name') or c_data.get('pushname') or c_data.get('number') or name

                pic_res = settings_model._openwa_api_request(
                    'GET', f'/sessions/{session.session_name}/contacts/{chat_jid}/profile-picture'
                )
                if pic_res.status_code == 200:
                    profile_pic = pic_res.json().get('url', '')
            except Exception as e:
                _logger.warning("Could not fetch contact info: %s", e)

            chat = OpenwaChat.create({
                'name': name,
                'jid': chat_jid,
                'session_id': session.id,
                'unread_count': 0,
                'last_message_body': '',
                'profile_pic_url': profile_pic,
            })

        direction = 'outbound' if from_me else 'inbound'
        body = msg_data.get('body', '')
        msg_type = 'text'
        attachment = False
        media = msg_data.get('media')

        if msg_data.get('type') == 'image' or (media and media.get('mimetype', '').startswith('image/')):
            msg_type = 'image'
            if not body or body == 'undefined':
                body = '[Image]'
            if media and media.get('data'):
                attachment = request.env['ir.attachment'].sudo().create({
                    'name': media.get('filename') or 'image.png',
                    'type': 'binary',
                    'datas': media.get('data'),
                    'res_model': 'openwa.message',
                    'public': True,
                })
        elif msg_data.get('type') == 'document' or media:
            msg_type = 'document'
            filename = media.get('filename') if media else 'document.pdf'
            if not body or body == 'undefined':
                body = filename or '[Document]'
            if media and media.get('data'):
                attachment = request.env['ir.attachment'].sudo().create({
                    'name': filename,
                    'type': 'binary',
                    'datas': media.get('data'),
                    'res_model': 'openwa.message',
                    'public': True,
                })

        new_msg = OpenwaMsg.create({
            'chat_id': chat.id,
            'body': body,
            'type': msg_type,
            'direction': direction,
            'timestamp': fields.Datetime.now(),
            'wa_message_id': wa_message_id,
            'attachment_id': attachment.id if attachment else False,
        })
        if attachment:
            attachment.write({'res_id': new_msg.id})

        chat_vals = {'last_message_body': body, 'last_message_date': fields.Datetime.now()}
        if direction == 'inbound':
            chat_vals['unread_count'] = chat.unread_count + 1
        chat.write(chat_vals)

        new_msg._broadcast_message(new_msg)

        return request.make_response(
            json.dumps({'status': 'success', 'message_id': new_msg.id}),
            headers=[('Content-Type', 'application/json')]
        )
