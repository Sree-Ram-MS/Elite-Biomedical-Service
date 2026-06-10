# -*- coding: utf-8 -*-
from odoo import models, fields, api

class GenerateServiceLogWizard(models.TransientModel):
    _name = 'generate.service.log.wizard'
    _description = 'Generate Service Log Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    base_date = fields.Date(string='Base Date', default=fields.Date.context_today, required=True)

    def action_generate(self):
        self.ensure_one()
        self.sale_order_id.action_generate_service_log(base_date=self.base_date)
        return {'type': 'ir.actions.act_window_close'}
