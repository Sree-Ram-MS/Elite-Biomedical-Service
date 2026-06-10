import json
import logging
import functools
from odoo import http
from odoo.http import request
import odoo

_logger = logging.getLogger(__name__)

def validate_token(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # OPTIONS requests are preflight calls and should proceed unchecked to return headers
        if request.httprequest.method == 'OPTIONS':
            return func(*args, **kwargs)
            
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
            
        # Check if the user is the public user
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
            
        return func(*args, **kwargs)
    return wrapper

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
                'currency_symbol': user.company_id.currency_id.symbol or '',
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
    @validate_token
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

        try:
            # Get allowed company IDs for session
            company_ids = tuple(request.env.companies.ids or [request.env.company.id])
            lang = request.env.lang or 'en_US'
            cr = request.env.cr

            # Get company currency symbol as guaranteed fallback
            company_currency_symbol = request.env.company.currency_id.symbol or ''

            # 1. Fetch Sale Orders
            cr.execute("""
                SELECT 
                    so.id, 
                    so.name, 
                    so.date_order, 
                    so.amount_total, 
                    so.amount_untaxed, 
                    so.amount_tax, 
                    so.user_id, 
                    rp_user.name as salesperson, 
                    apt.name as payment_term, 
                    so.validity_date, 
                    so.state, 
                    rp_cust.name as partner_name,
                    COALESCE(curr.symbol, comp_curr.symbol, '') as currency_symbol
                FROM sale_order so
                LEFT JOIN res_users u ON so.user_id = u.id
                LEFT JOIN res_partner rp_user ON u.partner_id = rp_user.id
                LEFT JOIN account_payment_term apt ON so.payment_term_id = apt.id
                LEFT JOIN res_partner rp_cust ON so.partner_id = rp_cust.id
                LEFT JOIN res_currency curr ON so.currency_id = curr.id
                LEFT JOIN res_company rc ON so.company_id = rc.id
                LEFT JOIN res_currency comp_curr ON rc.currency_id = comp_curr.id
                WHERE so.company_id IN %s
                ORDER BY so.date_order DESC, so.id DESC
            """, (company_ids,))
            
            orders = cr.dictfetchall()
            order_ids = tuple(o['id'] for o in orders)

            # Initialize child collections
            lines_by_order = {}
            expenses_by_order = {}
            invoices_by_order = {}
            service_logs_by_order = {}

            if order_ids:
                # 2. Fetch Order Lines (using sol.name which contains name & variant)
                cr.execute("""
                    SELECT 
                        sol.id, 
                        sol.order_id,
                        sol.name as product_name, 
                        sol.product_uom_qty as quantity, 
                        sol.price_unit, 
                        sol.price_subtotal
                    FROM sale_order_line sol
                    WHERE sol.order_id IN %s
                    ORDER BY sol.sequence, sol.id
                """, (order_ids,))
                for line in cr.dictfetchall():
                    order_id = line['order_id']
                    lines_by_order.setdefault(order_id, []).append({
                        'id': line['id'],
                        'product_name': (line['product_name'] or '').strip(),
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        'price_subtotal': line['price_subtotal'],
                    })

                # 3. Fetch Expenses
                cr.execute("""
                    SELECT 
                        e.id, 
                        e.sale_order_id,
                        e.expense_date, 
                        et.name as expense_type_name, 
                        e.description, 
                        e.amount, 
                        curr.symbol as currency_symbol, 
                        e.payment_state, 
                        emp.name as employee_name, 
                        e.notes
                    FROM biomedical_sale_expense e
                    LEFT JOIN biomedical_expense_type et ON e.expense_type_id = et.id
                    LEFT JOIN res_currency curr ON e.currency_id = curr.id
                    LEFT JOIN hr_employee emp ON e.employee_id = emp.id
                    WHERE e.sale_order_id IN %s
                    ORDER BY e.expense_date DESC, e.id DESC
                """, (order_ids,))
                for exp in cr.dictfetchall():
                    order_id = exp['sale_order_id']
                    expenses_by_order.setdefault(order_id, []).append({
                        'id': exp['id'],
                        'expense_date': exp['expense_date'].isoformat() if exp['expense_date'] else None,
                        'expense_type_name': exp['expense_type_name'] or '',
                        'description': exp['description'] or '',
                        'amount': exp['amount'],
                        'currency_symbol': exp['currency_symbol'] or company_currency_symbol,
                        'payment_state': exp['payment_state'],
                        'employee_name': exp['employee_name'] or '',
                        'notes': exp['notes'] or '',
                    })

                # 4. Fetch Invoices (both regular and service invoices via UNION query)
                cr.execute("""
                    WITH linked_invoices AS (
                        SELECT sol.order_id, am.id as move_id
                        FROM account_move am
                        INNER JOIN account_move_line aml ON aml.move_id = am.id
                        INNER JOIN sale_order_line_invoice_rel rel ON rel.invoice_line_id = aml.id
                        INNER JOIN sale_order_line sol ON sol.id = rel.order_line_id
                        WHERE sol.order_id IN %s
                        
                        UNION
                        
                        SELECT bsl.sale_order_id as order_id, bsl.invoice_id as move_id
                        FROM biomedical_service_log bsl
                        WHERE bsl.sale_order_id IN %s AND bsl.invoice_id IS NOT NULL
                    )
                    SELECT 
                        li.order_id,
                        am.id,
                        am.name,
                        am.invoice_date,
                        am.amount_total,
                        am.state,
                        am.payment_state,
                        curr.symbol as currency_symbol
                    FROM linked_invoices li
                    INNER JOIN account_move am ON li.move_id = am.id
                    LEFT JOIN res_currency curr ON am.currency_id = curr.id
                    ORDER BY am.invoice_date DESC, am.id DESC
                """, (order_ids, order_ids))
                for inv in cr.dictfetchall():
                    order_id = inv['order_id']
                    invoices_by_order.setdefault(order_id, []).append({
                        'id': inv['id'],
                        'name': inv['name'] or '',
                        'invoice_date': inv['invoice_date'].isoformat() if inv['invoice_date'] else None,
                        'amount_total': float(inv['amount_total']) if inv['amount_total'] is not None else 0.0,
                        'state': inv['state'],
                        'payment_state': inv['payment_state'],
                        'currency_symbol': inv['currency_symbol'] or company_currency_symbol,
                    })

                # 5. Fetch Service Logs
                cr.execute("""
                    SELECT 
                        bsl.id,
                        bsl.sale_order_id,
                        bsl.name,
                        bsl.service_name,
                        emp.name as employee_name,
                        bsl.scheduled_date,
                        bsl.completed_date,
                        bsl.current_used_hours,
                        bsl.interval_hours,
                        bsl.notes,
                        bsl.state,
                        bsl.invoice_id,
                        am.name as invoice_name
                    FROM biomedical_service_log bsl
                    LEFT JOIN hr_employee emp ON bsl.employee_id = emp.id
                    LEFT JOIN account_move am ON bsl.invoice_id = am.id
                    WHERE bsl.sale_order_id IN %s
                    ORDER BY bsl.scheduled_date DESC, bsl.id DESC
                """, (order_ids,))
                service_logs = cr.dictfetchall()
                service_log_ids = tuple(log['id'] for log in service_logs)

                # Initialize service log lines mapping
                lines_by_log = {}
                if service_log_ids:
                    # 6. Fetch Service Log Lines (with variant attributes)
                    cr.execute("""
                        SELECT 
                            bsll.id,
                            bsll.service_log_id,
                            COALESCE(pp.default_code, '') || CASE WHEN COALESCE(pp.default_code,'') != '' THEN ' ' ELSE '' END ||
                            COALESCE(pt.name->>%s, pt.name->>'en_US', '') as product_name,
                            bsll.qty,
                            bsll.price_unit,
                            bsll.price_subtotal,
                            STRING_AGG(
                                COALESCE(pav.name->>%s, pav.name->>'en_US', ''),
                                ', ' ORDER BY ptav.id
                            ) FILTER (WHERE pav.id IS NOT NULL) as variant_attributes
                        FROM biomedical_service_log_line bsll
                        LEFT JOIN product_product pp ON bsll.product_id = pp.id
                        LEFT JOIN product_template pt ON pp.product_tmpl_id = pt.id
                        LEFT JOIN product_variant_combination pvc ON pvc.product_product_id = pp.id
                        LEFT JOIN product_template_attribute_value ptav ON ptav.id = pvc.product_template_attribute_value_id
                        LEFT JOIN product_attribute_value pav ON pav.id = ptav.product_attribute_value_id
                        WHERE bsll.service_log_id IN %s
                        GROUP BY bsll.id, bsll.service_log_id, pp.default_code, pt.name, bsll.qty, bsll.price_unit, bsll.price_subtotal
                        ORDER BY bsll.id
                    """, (lang, lang, service_log_ids))
                    for line in cr.dictfetchall():
                        log_id = line['service_log_id']
                        base_name = line['product_name'].strip()
                        attrs = line.get('variant_attributes') or ''
                        full_name = f"{base_name} ({attrs})" if attrs else base_name
                        lines_by_log.setdefault(log_id, []).append({
                            'id': line['id'],
                            'product_name': full_name,
                            'qty': line['qty'],
                            'price_unit': line['price_unit'],
                            'price_subtotal': line['price_subtotal'],
                        })

                for log in service_logs:
                    order_id = log['sale_order_id']
                    # Find order currency symbol for this log's order
                    order_currency = next((o['currency_symbol'] for o in orders if o['id'] == order_id), company_currency_symbol)
                    service_logs_by_order.setdefault(order_id, []).append({
                        'id': log['id'],
                        'name': log['name'] or '',
                        'service_name': log['service_name'] or '',
                        'employee_name': log['employee_name'] or '',
                        'scheduled_date': log['scheduled_date'].isoformat() if log['scheduled_date'] else None,
                        'completed_date': log['completed_date'].isoformat() if log['completed_date'] else None,
                        'current_used_hours': log['current_used_hours'] or 0.0,
                        'interval_hours': log['interval_hours'] or 0.0,
                        'notes': log['notes'] or '',
                        'state': log['state'],
                        'invoice_id': log['invoice_id'],
                        'invoice_name': log['invoice_name'] or '',
                        'currency_symbol': order_currency,
                        'service_lines': lines_by_log.get(log['id'], []),
                    })

            # 7. Assemble final list of orders
            orders_data = []
            for order in orders:
                oid = order['id']
                orders_data.append({
                    'id': oid,
                    'name': order['name'],
                    'partner_name': order['partner_name'] or 'Unknown Customer',
                    'date_order': order['date_order'].isoformat() if order['date_order'] else None,
                    'amount_total': float(order['amount_total']) if order['amount_total'] is not None else 0.0,
                    'amount_untaxed': float(order['amount_untaxed']) if order['amount_untaxed'] is not None else 0.0,
                    'amount_tax': float(order['amount_tax']) if order['amount_tax'] is not None else 0.0,
                    'user_id': order['user_id'],
                    'salesperson': order['salesperson'] or '',
                    'payment_term': order['payment_term'] or '',
                    'validity_date': order['validity_date'].isoformat() if order['validity_date'] else None,
                    'state': order['state'],
                    'currency_symbol': order['currency_symbol'] or company_currency_symbol,
                    'order_lines': lines_by_order.get(oid, []),
                    'expenses': expenses_by_order.get(oid, []),
                    'invoices': invoices_by_order.get(oid, []),
                    'service_logs': service_logs_by_order.get(oid, []),
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
    @validate_token
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

        try:
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
                if 'image_1920' in body:
                    partner_vals['image_1920'] = body['image_1920']

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
                'currency_symbol': user.company_id.currency_id.symbol or '',
                'street': user.partner_id.street or '',
                'street2': user.partner_id.street2 or '',
                'city': user.partner_id.city or '',
                'zip': user.partner_id.zip or '',
                'website': user.partner_id.website or '',
                'function': user.partner_id.function or '',
                'image_128': user.partner_id.image_128.decode('utf-8') if user.partner_id.image_128 else '',
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

    @http.route('/api/sale_order/<int:order_id>/pdf', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    @validate_token
    def api_sale_order_pdf(self, order_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie'),
                ]
            )

        try:
            # Check if order exists and is readable by the user
            order = request.env['sale.order'].browse(order_id)
            if not order.exists():
                return request.make_response(
                    json.dumps({'error': 'Sale order not found'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=404
                )

            # Generate PDF
            pdf_content, _ = request.env['ir.actions.report']._render_qweb_pdf('sale.report_saleorder', [order_id])
            
            filename = f"Sale_Order_{order.name}.pdf"
            headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
                ('Access-Control-Allow-Origin', '*'),
            ]
            return request.make_response(pdf_content, headers=headers)
        except Exception as e:
            _logger.exception("Failed to generate PDF for sale order")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

    @http.route('/api/invoice/<int:invoice_id>/pdf', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    @validate_token
    def api_invoice_pdf(self, invoice_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie'),
                ]
            )

        try:
            # Check if invoice exists and is readable by the user
            invoice = request.env['account.move'].browse(invoice_id)
            if not invoice.exists():
                return request.make_response(
                    json.dumps({'error': 'Invoice not found'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=404
                )

            # Generate PDF
            pdf_content, _ = request.env['ir.actions.report']._render_qweb_pdf('account.report_invoice', [invoice_id])
            
            filename = f"Invoice_{invoice.name.replace('/', '_')}.pdf"
            headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
                ('Access-Control-Allow-Origin', '*'),
            ]
            return request.make_response(pdf_content, headers=headers)
        except Exception as e:
            _logger.exception("Failed to generate PDF for invoice")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

    @http.route('/api/service_log/<int:log_id>/pdf', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False)
    @validate_token
    def api_service_log_pdf(self, log_id, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response(
                '',
                headers=[
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, Cookie'),
                ]
            )

        try:
            # Check if service log exists and is readable by the user
            log = request.env['biomedical.service.log'].browse(log_id)
            if not log.exists():
                return request.make_response(
                    json.dumps({'error': 'Service log not found'}),
                    headers=[
                        ('Content-Type', 'application/json'),
                        ('Access-Control-Allow-Origin', '*'),
                    ],
                    status=404
                )

            # Generate PDF
            pdf_content, _ = request.env['ir.actions.report']._render_qweb_pdf('biomedical_service.report_service_log', [log_id])
            
            filename = f"Service_Log_{log.name}.pdf"
            headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
                ('Access-Control-Allow-Origin', '*'),
            ]
            return request.make_response(pdf_content, headers=headers)
        except Exception as e:
            _logger.exception("Failed to generate PDF for service log")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*'),
                ],
                status=500
            )

