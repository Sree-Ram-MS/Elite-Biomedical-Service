# -*- coding: utf-8 -*-
from odoo import models, fields, api
class BiomedicalExpenseType(models.Model):
    _name = 'biomedical.expense.type'
    _description = 'Expense Type Master'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code')

class BiomedicalSaleExpense(models.Model):
    _name = 'biomedical.sale.expense'
    _description = 'Sale Order Expense'
    _order = 'expense_date desc, id desc'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    expense_date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    expense_type_id = fields.Many2one('biomedical.expense.type', string='Expense Type', required=True)
    description = fields.Char(string='Description', required=False)
    amount = fields.Float(string='Amount', required=True)
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    payment_state = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid')
    ], string='Payment State', default='unpaid', required=True, copy=False)
    payment_id = fields.Many2one('account.payment', string='Payment Entry', readonly=True, copy=False)
    notes = fields.Text(string='Notes')
    
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company
    )
    user_id = fields.Many2one(
        'res.users', 
        string='Logged By', 
        required=True, 
        default=lambda self: self.env.user,
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee', 
        string='Employee', 
        required=True,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env.user.employee_id
    )

    def action_register_payment(self):
        self.ensure_one()
        if self.payment_state == 'paid':
            return
        return {
            'name': 'Register Expense Payment',
            'type': 'ir.actions.act_window',
            'res_model': 'biomedical.expense.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_expense_id': self.id,
                'default_amount': self.amount,
                'default_currency_id': self.currency_id.id,
                'default_communication': f"Expense Payment: {self.description or ''} for {self.sale_order_id.name}",
            }
        }

    def action_view_payment(self):
        self.ensure_one()
        if not self.payment_id:
            return
        return {
            'name': 'Expense Payment',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
            'target': 'current',
        }
