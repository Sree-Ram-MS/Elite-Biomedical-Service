# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    expense_ids = fields.One2many(
        'biomedical.expense', 
        'sale_order_id', 
        string='Expenses'
    )
    
    expense_total = fields.Monetary(
        string='Expenses Total', 
        compute='_compute_expense_total', 
        currency_field='currency_id'
    )

    @api.depends('expense_ids.amount')
    def _compute_expense_total(self):
        for order in self:
            order.expense_total = sum(order.expense_ids.mapped('amount'))
Class_name = 'SaleOrder'
