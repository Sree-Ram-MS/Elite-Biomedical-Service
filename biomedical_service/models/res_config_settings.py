# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    reminder_enabled = fields.Boolean(
        string='Enable Service Reminders',
        config_parameter='biomedical.reminder_enabled'
    )
    reminder_days_before = fields.Integer(
        string='Remind Before (Days)',
        config_parameter='biomedical.reminder_days_before',
        default=7
    )
    reminder_user_ids = fields.Many2many(
        'res.users',
        string='Notify Users'
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        user_ids_str = params.get_param('biomedical.reminder_user_ids', '')
        user_ids = [int(x) for x in user_ids_str.split(',') if x.isdigit()]
        res.update(
            reminder_user_ids=[Command.set(user_ids)]
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        user_ids_str = ','.join(map(str, self.reminder_user_ids.ids))
        self.env['ir.config_parameter'].sudo().set_param('biomedical.reminder_user_ids', user_ids_str)
