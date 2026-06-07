# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command
from odoo.exceptions import UserError

class BiomedicalExpense(models.Model):
    _name = 'biomedical.expense'
    _description = 'Biomedical Expense'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    
    user_id = fields.Many2one(
        'res.users', 
        string='User', 
        required=True, 
        default=lambda self: self.env.user
    )
    
    partner_id = fields.Many2one(
        'res.partner', 
        string='Payee / Vendor', 
        default=lambda self: self.env.user.partner_id
    )
    
    expense_type_id = fields.Many2one('biomedical.expense.type', string='Expense Type', required=True)
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        default=lambda self: self.env.company.currency_id
    )
    
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    
    attachment = fields.Binary(string='Attachment')
    attachment_name = fields.Char(string='Attachment Name')
    
    move_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True, copy=False)
    payment_state = fields.Selection(related='move_id.payment_state', string='Payment Status')
    bill_state = fields.Selection(related='move_id.state', string='Bill Status')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('billed', 'Billed')
    ], string='Status', compute='_compute_state', store=True, default='draft')

    @api.depends('move_id')
    def _compute_state(self):
        for rec in self:
            if rec.move_id:
                rec.state = 'billed'
            else:
                rec.state = 'draft'

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self.partner_id = self.user_id.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('biomedical.expense') or 'New'
        return super(BiomedicalExpense, self).create(vals_list)

    def action_create_vendor_bill(self):
        self.ensure_one()
        if self.move_id:
            raise UserError("A Vendor Bill has already been generated for this expense.")

        # Determine partner (payee)
        partner = self.partner_id or self.user_id.partner_id
        if not partner:
            partner = self.env.company.partner_id

        if not partner:
            raise UserError("No partner could be resolved for this expense.")

        # Determine account
        account = self.expense_type_id.account_id
        if not account:
            account = self.env['account.account'].search([
                ('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))
            ], limit=1)

        if not account:
            raise UserError("Please configure an Expense Account on the Expense Type or ensure at least one Expense Account exists.")

        # Create the Vendor Bill (account.move of type 'in_invoice')
        move_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': self.date,
            'ref': f"Expense: {self.name} for {self.sale_order_id.name}",
            'invoice_line_ids': [Command.create({
                'name': f"{self.expense_type_id.name} - {self.sale_order_id.name}",
                'quantity': 1.0,
                'price_unit': self.amount,
                'account_id': account.id,
            })],
        }
        
        move = self.env['account.move'].create(move_vals)
        self.move_id = move.id
        
        # Attach the file upload to the Vendor Bill if present
        if self.attachment and self.attachment_name:
            self.env['ir.attachment'].create({
                'name': self.attachment_name,
                'type': 'binary',
                'datas': self.attachment,
                'res_model': 'account.move',
                'res_id': move.id,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_vendor_bill(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError("No Vendor Bill is linked to this expense.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bill',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }
Class_name = 'BiomedicalExpense'
