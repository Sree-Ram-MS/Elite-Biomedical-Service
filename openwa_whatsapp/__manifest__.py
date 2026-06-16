{
    'name': 'OpenWA WhatsApp Integration',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Customer Relationship Management',
    'summary': 'Per-user WhatsApp integration using self-hosted OpenWA gateway',
    'description': """
        Integrate Odoo with a self-hosted NestJS OpenWA WhatsApp API Gateway.
        - Each user manages their own WhatsApp session independently
        - Full session lifecycle: create → start engine → scan QR → connected
        - Dedicated "My Session" menu with live status, QR scanner, start/stop
        - Real-time inbound/outbound messages in WhatsApp Web-like interface
        - Messages scoped per user session via Odoo Bus
        - Global settings (API URL, API Key) managed by admins in res.config.settings
    """,
    'author': 'Antigravity & Sree Ram M S',
    'depends': ['base', 'mail', 'web', 'bus'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/openwa_session_views.xml',
        'views/openwa_whatsapp_views.xml',
        'wizards/openwa_connection_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'openwa_whatsapp/static/src/js/openwa_session.js',
            'openwa_whatsapp/static/src/xml/openwa_session.xml',
            'openwa_whatsapp/static/src/js/openwa_chat.js',
            'openwa_whatsapp/static/src/xml/openwa_chat.xml',
            'openwa_whatsapp/static/src/css/openwa_chat.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
