# -*- coding: utf-8 -*-
from odoo import models, fields

class BiomedicalServiceConfig(models.Model):
    _name = 'biomedical.service.config'
    _description = 'Product Service Configuration'
    _order = 'sequence, id'
    _rec_name = 'service_name'

    product_id = fields.Many2one(
        'product.template', 
        string='Product Template', 
        required=True, 
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    service_name = fields.Char(string='Service Name', required=True)
    interval_days = fields.Integer(string='Interval (Days)', default=180, required=True)
    interval_hours = fields.Float(string='Interval (Hours)', default=0.0)
    description = fields.Text(string='Description')
