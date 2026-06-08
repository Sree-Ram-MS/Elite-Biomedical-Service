import json
import logging
from odoo import http
from odoo.http import request
import odoo

_logger = logging.getLogger(__name__)

class BiomedicalApiController(http.Controller):

    @http.route('/api/auth/databases', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def api_databases(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
                ]
            )

        try:
            from odoo.service.db import list_dbs
            dbs = list_dbs()
            return request.make_response(
                json.dumps({'databases': dbs}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ]
            )
        except Exception as e:
            _logger.exception("Failed to fetch databases")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

    @http.route('/api/auth/login', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def api_login(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'POST, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
                ]
            )

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(
                json.dumps({'error': 'Invalid JSON body'}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=400
            )

        db = body.get('db')
        login = body.get('login')
        password = body.get('password')

        if not db or not login or not password:
            return request.make_response(
                json.dumps({'error': 'Missing db, login, or password parameters'}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=400
            )

        # Check database list
        try:
            from odoo.service.db import list_dbs
            if db not in list_dbs():
                return request.make_response(
                    json.dumps({'error': f"Database '{db}' not found on server"}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=400
                )
        except Exception:
            pass # Fallback if list_dbs is disabled

        try:
            # Verify request database matches the login database
            if not request.db or request.db != db:
                return request.make_response(
                    json.dumps({'error': f"Database mismatch. Please ensure Odoo runs on database '{db}' by appending '?db={db}' to the login request URL."}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=400
                )

            # Authenticate the user using request.env (which has the active request cursor)
            credential = {'login': login, 'password': password, 'type': 'password'}
            auth_info = request.session.authenticate(request.env, credential)
            
            uid = auth_info.get('uid')
            if not uid:
                return request.make_response(
                    json.dumps({'error': 'Authentication failed'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=401
                )
            
            # Fetch user details using request.env
            user = request.env['res.users'].browse(uid)
            user_name = user.name
            company_name = user.company_id.name
            
            # Response containing session_id and user details
            result = {
                'session_id': request.session.sid,
                'uid': uid,
                'name': user_name,
                'login': login,
                'company': company_name,
                'db': db,
            }
            
            headers = [
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*'),
            ]
            return request.make_response(json.dumps(result), headers=headers)

        except odoo.exceptions.AccessDenied:
            return request.make_response(
                json.dumps({'error': 'Wrong login or password'}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=401
            )
        except Exception as e:
            _logger.exception("Login failure")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

    @http.route('/api/sale_orders', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    def api_sale_orders(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie'),
                ]
            )

        # Check authentication using session
        if not request.session.uid:
            return request.make_response(
                json.dumps({'error': 'Unauthorized - Session expired or invalid'}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=401
            )

        try:
            # Check public user
            public_user = request.env.ref('base.public_user', raise_if_not_found=False)
            if public_user and request.env.user.id == public_user.id:
                return request.make_response(
                    json.dumps({'error': 'Unauthorized - Public user session'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=401
                )

            # Search sale orders for the authenticated user
            # Since request.env is configured with request.session.uid,
            # standard record rules automatically apply!
            sale_orders = request.env['sale.order'].search([], order='date_order desc')
            
            orders_data = []
            for order in sale_orders:
                orders_data.append({
                    'id': order.id,
                    'name': order.name,
                    'partner_name': order.partner_id.name,
                    'date_order': order.date_order.isoformat() if order.date_order else None,
                    'amount_total': order.amount_total,
                    'state': order.state,
                })
                
            return request.make_response(
                json.dumps({'sale_orders': orders_data}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ]
            )
        except Exception as e:
            _logger.exception("Failed to retrieve sale orders")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )


    @http.route('/api/user/profile', type='http', auth='public', methods=['GET', 'POST', 'OPTIONS'], csrf=False)
    def api_user_profile(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie'),
                ]
            )

        # Check authentication using session
        if not request.session.uid:
            return request.make_response(
                json.dumps({'error': 'Unauthorized - Session expired or invalid'}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=401
            )

        try:
            # Check public user
            public_user = request.env.ref('base.public_user', raise_if_not_found=False)
            if public_user and request.env.user.id == public_user.id:
                return request.make_response(
                    json.dumps({'error': 'Unauthorized - Public user session'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=401
                )

            user = request.env.user

            if request.httprequest.method == 'POST':
                try:
                    body = json.loads(request.httprequest.data)
                except Exception:
                    return request.make_response(
                        json.dumps({'error': 'Invalid JSON body'}),
                        headers=[
                            ('Content-Type', 'application/json'),
                            ('Access-Control-Allow-Origin', '*'),
                        ],
                        status=400
                    )

                # Update fields
                partner_vals = {}
                if 'name' in body and body['name']:
                    partner_vals['name'] = body['name'].strip()
                if 'email' in body:
                    partner_vals['email'] = body['email'].strip()
                if 'phone' in body:
                    partner_vals['phone'] = body['phone'].strip()
                if 'street' in body:
                    partner_vals['street'] = body['street'].strip()
                if 'street2' in body:
                    partner_vals['street2'] = body['street2'].strip()
                if 'city' in body:
                    partner_vals['city'] = body['city'].strip()
                if 'zip' in body:
                    partner_vals['zip'] = body['zip'].strip()
                if 'website' in body:
                    partner_vals['website'] = body['website'].strip()
                if 'function' in body:
                    partner_vals['function'] = body['function'].strip()

                if partner_vals:
                    user.partner_id.write(partner_vals)

            # Return profile details
            profile_data = {
                'id': user.id,
                'name': user.name,
                'login': user.login,
                'email': user.email or '',
                'phone': user.partner_id.phone or '',
                'company': user.company_id.name or '',
                'street': user.partner_id.street or '',
                'street2': user.partner_id.street2 or '',
                'city': user.partner_id.city or '',
                'zip': user.partner_id.zip or '',
                'website': user.partner_id.website or '',
                'function': user.partner_id.function or '',
            }

            return request.make_response(
                json.dumps(profile_data),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ]
            )
        except Exception as e:
            _logger.exception("Failed to fetch or update user profile")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

