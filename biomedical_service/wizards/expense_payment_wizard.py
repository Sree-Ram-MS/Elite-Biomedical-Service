# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class BiomedicalExpensePaymentWizard(models.TransientModel):
    _name = 'biomedical.expense.payment.wizard'
    _description = 'Register Expense Payment'

    expense_id = fields.Many2one('biomedical.sale.expense', string='Expense', required=True)
    journal_id = fields.Many2one(
        'account.journal', 
        string='Payment Journal', 
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]"
    )
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True)
    amount = fields.Float(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    communication = fields.Char(string='Memo')

    @api.model
    def default_get(self, fields_list):
        res = super(BiomedicalExpensePaymentWizard, self).default_get(fields_list)
        journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if journal:
            res['journal_id'] = journal.id
        return res

    def action_register(self):
        self.ensure_one()
        if self.expense_id.payment_state == 'paid':
            raise UserError("This expense has already been paid.")

        # Resolve partner (supplier/employee)
        partner = False
        employee = self.expense_id.employee_id
        if employee:
            if hasattr(employee, 'address_home_id') and employee.address_home_id:
                partner = employee.address_home_id
            elif hasattr(employee, 'work_contact_id') and employee.work_contact_id:
                partner = employee.work_contact_id
            elif employee.user_id and employee.user_id.partner_id:
                partner = employee.user_id.partner_id
        
        if not partner:
            partner = self.expense_id.user_id.partner_id
            
        if not partner:
            partner = self.expense_id.company_id.partner_id

        if not partner:
            raise UserError("Unable to resolve a partner/payee for the expense payment.")

        # Create account.payment
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id,
            'journal_id': self.journal_id.id,
            'amount': self.amount,
            'date': self.payment_date,
            'memo': self.communication or f"Expense Payment: {self.expense_id.description or ''}",
            'currency_id': self.currency_id.id,
        }
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # Link to expense and mark as paid
        self.expense_id.write({
            'payment_id': payment.id,
            'payment_state': 'paid'
        })

        return {'type': 'ir.actions.act_window_close'}
