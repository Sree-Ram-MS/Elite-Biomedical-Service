# -*- coding: utf-8 -*-
from odoo import models, fields, api

class BiomedicalExpenseType(models.Model):
    _name = 'biomedical.expense.type'
    _description = 'Biomedical Expense Type'

    name = fields.Char(string='Expense Type', required=True)
    description = fields.Text(string='Description')

    account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        required=True,
        domain="[('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))]",
        default=lambda self: self._default_account_id()
    )

    @api.model
    def _default_account_id(self):
        return self.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))
        ], limit=1)
Class_name = 'BiomedicalExpenseType'
