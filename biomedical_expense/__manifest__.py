{
    'name': 'Biomedical Expense System',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Track and pay expenses associated with Sale Orders separately.',
    'description': """
This module allows users to input expenses directly from a Sale Order.
Each expense can be billed separately using standard Vendor Bills (account.move)
without affecting the Sale Order total.
    """,
    'author': 'Sree Ram M S',
    'depends': ['sale_management', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/biomedical_expense_type_views.xml',
        'views/biomedical_expense_views.xml',
        'views/sale_order_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
