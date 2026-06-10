from odoo import models, fields, api, Command
from datetime import timedelta

class BiomedicalServiceLogLine(models.Model):
    _name = 'biomedical.service.log.line'
    _description = 'Service Log Line'

    service_log_id = fields.Many2one('biomedical.service.log', string='Service Log', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product / Equipment', required=True)
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    price_unit = fields.Float(string='Price', required=True)
    price_subtotal = fields.Float(string='Total', compute='_compute_price_subtotal', store=True)

    @api.depends('qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.qty * line.price_unit

class BiomedicalServiceLog(models.Model):
    _name = 'biomedical.service.log'
    _description = 'Service Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    service_config_id = fields.Many2one('biomedical.service.config', string='Service Configuration', ondelete='set null')
    service_name = fields.Char(string='Service Name', required=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', 
        string='Technician / Employee', 
        tracking=True,
        default=lambda self: self.env.user.employee_id or self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
    )
    scheduled_date = fields.Date(string='Scheduled Date', required=True, tracking=True)
    completed_date = fields.Date(string='Completed Date', tracking=True)
    current_used_hours = fields.Float(string='Current Used Hours')
    interval_hours = fields.Float(string='Interval Hours')
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('completed', 'Completed')
    ], string='Status', default='draft', required=True, tracking=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Service Invoice', readonly=True, copy=False)
    reminder_sent = fields.Boolean(string='Reminder Sent', default=False, copy=False)
    service_line_ids = fields.One2many('biomedical.service.log.line', 'service_log_id', string='Service Lines')

    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoice Count')

    @api.depends('invoice_id')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = 1 if rec.invoice_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('biomedical.service.log') or 'New'
        return super(BiomedicalServiceLog, self).create(vals_list)

    def action_complete(self):
        self.write({
            'state': 'completed',
            'completed_date': fields.Date.today()
        })

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            from odoo.exceptions import UserError
            raise UserError("An invoice has already been created for this service log.")
        if not self.service_line_ids:
            from odoo.exceptions import UserError
            raise UserError("Cannot create invoice for a service log with no lines.")

        sale_order = self.sale_order_id
        partner = sale_order.partner_id
        if not partner:
            from odoo.exceptions import UserError
            raise UserError("The associated Sale Order must have a customer.")

        # Create customer invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_origin': sale_order.name,
            'invoice_line_ids': [
                Command.create({
                    'product_id': line.product_id.id,
                    'name': f"{self.service_name} - {line.product_id.name}",
                    'quantity': line.qty,
                    'price_unit': line.price_unit,
                }) for line in self.service_line_ids
            ]
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({'invoice_id': invoice.id})
        
        return {
            'name': 'Customer Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return
        return {
            'name': 'Customer Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }

    @api.model
    def _cron_send_service_reminders(self):
        params = self.env['ir.config_parameter'].sudo()
        enabled = params.get_param('biomedical.reminder_enabled')
        if not enabled:
            return
        
        days_before = int(params.get_param('biomedical.reminder_days_before', 7))
        user_ids_str = params.get_param('biomedical.reminder_user_ids', '')
        user_ids = [int(x) for x in user_ids_str.split(',') if x.isdigit()]
        if not user_ids:
            return
            
        users = self.env['res.users'].browse(user_ids).exists()
        if not users:
            return
            
        target_date = fields.Date.today() + timedelta(days=days_before)
        logs = self.search([
            ('scheduled_date', '=', target_date),
            ('state', '=', 'draft'),
            ('reminder_sent', '=', False)
        ])
        
        for log in logs:
            partner_ids = users.mapped('partner_id').ids
            products_str = ", ".join(log.service_line_ids.mapped('product_id.display_name'))
            subject = f"Upcoming Service Reminder: {log.service_name} for {products_str}"
            body = f"""
                <p>Hello,</p>
                <p>This is a reminder for the upcoming service:</p>
                <ul>
                    <li><strong>Service Name:</strong> {log.service_name}</li>
                    <li><strong>Scheduled Date:</strong> {log.scheduled_date}</li>
                    <li><strong>Sale Order:</strong> {log.sale_order_id.name}</li>
                    <li><strong>Customer:</strong> {log.sale_order_id.partner_id.name}</li>
                    <li><strong>Products/Equipments:</strong> {products_str}</li>
                </ul>
            """
            log.message_notify(
                partner_ids=partner_ids,
                subject=subject,
                body=body,
                email_layout_xmlid='mail.mail_notification_layout_light',
            )
            log.reminder_sent = True
