# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command
from datetime import timedelta

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    service_log_generated = fields.Boolean(
        string='Service Logs Generated', 
        default=False, 
        copy=False
    )
    expense_ids = fields.One2many(
        'biomedical.sale.expense', 
        'sale_order_id', 
        string='Expenses'
    )
    service_log_ids = fields.One2many(
        'biomedical.service.log', 
        'sale_order_id', 
        string='Service Logs'
    )

    expense_count = fields.Integer(
        compute='_compute_expense_count_and_amount', 
        string='Expense Count'
    )
    expense_total_amount = fields.Float(
        compute='_compute_expense_count_and_amount', 
        string='Expense Total Amount'
    )
    service_log_count = fields.Integer(
        compute='_compute_service_log_count', 
        string='Service Log Count'
    )
    service_invoice_count = fields.Integer(
        compute='_compute_service_invoice_count', 
        string='Service Invoice Count'
    )

    @api.depends('expense_ids')
    def _compute_expense_count_and_amount(self):
        for order in self:
            order.expense_count = len(order.expense_ids)
            order.expense_total_amount = sum(order.expense_ids.mapped('amount'))

    @api.depends('service_log_ids')
    def _compute_service_log_count(self):
        for order in self:
            order.service_log_count = len(order.service_log_ids)

    @api.depends('service_log_ids.invoice_id')
    def _compute_service_invoice_count(self):
        for order in self:
            invoices = order.service_log_ids.mapped('invoice_id')
            order.service_invoice_count = len(invoices)

    @api.depends('order_line.invoice_lines.move_id', 'service_log_ids.invoice_id')
    def _get_invoiced(self):
        super()._get_invoiced()
        for order in self:
            service_invoices = order.service_log_ids.mapped('invoice_id')
            if service_invoices:
                order.invoice_ids = order.invoice_ids | service_invoices
                # Exclude service invoices from standard invoice_count
                product_invoices = order.invoice_ids.filtered(lambda m: m.id not in service_invoices.ids)
                order.invoice_count = len(product_invoices)

    def action_view_invoice(self, invoices=False):
        service_invoice_ids = self.service_log_ids.mapped('invoice_id').ids
        if not invoices:
            invoices = self.invoice_ids.filtered(lambda m: m.id not in service_invoice_ids)
        else:
            invoices = invoices.filtered(lambda m: m.id not in service_invoice_ids)
        return super(SaleOrder, self).action_view_invoice(invoices=invoices)

    # action_view_expenses removed as it is now in a standalone menu.

    def action_view_service_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("biomedical_service.action_biomedical_service_log")
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {'default_sale_order_id': self.id}
        return action

    # action_view_service_invoices removed as the button box is removed.

    def action_generate_service_log_wizard(self):
        self.ensure_one()
        if self.service_log_generated:
            return
        return {
            'name': 'Generate Service Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'generate.service.log.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_base_date': self.date_order.date() if self.date_order else fields.Date.today(),
            }
        }

    def action_generate_service_log(self, base_date=False):
        for order in self:
            if order.service_log_generated:
                continue
            if not base_date:
                base_date = order.date_order.date() if order.date_order else fields.Date.today()
            
            # Map of (service_name, scheduled_date, interval_hours, config_id) -> dummy
            log_groups = {}
            for line in order.order_line:
                product_tmpl = line.product_id.product_tmpl_id
                for config in product_tmpl.service_config_ids:
                    scheduled = base_date + timedelta(days=config.interval_days)
                    key = (config.service_name, scheduled, config.interval_hours, config.id)
                    log_groups[key] = True
            
            # Fetch reminder users
            params = self.env['ir.config_parameter'].sudo()
            user_ids_str = params.get_param('biomedical.reminder_user_ids', '')
            user_ids = [int(x) for x in user_ids_str.split(',') if x.isdigit()]
            users = self.env['res.users'].browse(user_ids).exists()
            activity_type_todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)

            for key in log_groups.keys():
                service_name, scheduled, interval_hours, config_id = key
                log = self.env['biomedical.service.log'].create({
                    'sale_order_id': order.id,
                    'service_config_id': config_id,
                    'service_name': service_name,
                    'scheduled_date': scheduled,
                    'interval_hours': interval_hours,
                    'state': 'draft',
                    'service_line_ids': [],
                })
                # Create activity for reminder users
                if activity_type_todo:
                    for user in users:
                        self.env['mail.activity'].create({
                            'activity_type_id': activity_type_todo.id,
                            'res_id': log.id,
                            'res_model_id': self.env['ir.model']._get('biomedical.service.log').id,
                            'user_id': user.id,
                            'summary': f"Todo for service: {log.service_name}",
                            'note': f"Scheduled date: {scheduled}",
                            'date_deadline': scheduled,
                        })
            order.service_log_generated = True
