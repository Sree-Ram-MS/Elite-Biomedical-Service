# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command
from odoo.exceptions import UserError

class BiomedicalServiceInvoiceWizard(models.TransientModel):
    _name = 'biomedical.service.invoice.wizard'
    _description = 'Create Service Invoice Wizard'

    service_log_id = fields.Many2one('biomedical.service.log', string='Service Log', required=True)
    service_product_id = fields.Many2one(
        'product.product', 
        string='Service Product', 
        required=True,
        domain="[('type', '=', 'service')]"
    )
    amount = fields.Float(string='Invoice Amount', required=True)
    invoice_date = fields.Date(string='Invoice Date', default=fields.Date.context_today, required=True)
    description = fields.Char(string='Description', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(BiomedicalServiceInvoiceWizard, self).default_get(fields_list)
        product = self.env['product.product'].search([('type', '=', 'service')], limit=1)
        if product:
            res['service_product_id'] = product.id
        return res

    def action_create_invoice(self):
        self.ensure_one()
        log = self.service_log_id
        if log.invoice_id:
            raise UserError("An invoice has already been created for this service log.")

        sale_order = log.sale_order_id
        partner = sale_order.partner_id
        if not partner:
            raise UserError("The associated Sale Order must have a customer.")

        # Create customer invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': self.invoice_date,
            'invoice_origin': sale_order.name,
            'invoice_line_ids': [
                Command.create({
                    'product_id': self.service_product_id.id,
                    'name': self.description or f"{log.service_name} - {sale_order.name}",
                    'quantity': 1.0,
                    'price_unit': self.amount,
                })
            ]
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Link back to service log
        log.write({
            'invoice_id': invoice.id,
        })

        return {
            'name': 'Customer Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }
