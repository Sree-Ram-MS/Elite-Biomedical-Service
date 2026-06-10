# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    service_config_ids = fields.One2many(
        'biomedical.service.config', 
        'product_id', 
        string='Service Configurations'
    )
