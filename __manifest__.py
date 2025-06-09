{
    'name': 'Website Category Sync',
    'version': '18.0.1.0.5',
    'category': 'Website',
    'summary': 'Synchronizes inventory product category hierarchy to website categories.',
    'author': 'GitHub Copilot',
    'website': '',
    'depends': [
        'product',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sync_views.xml',
        'views/product_tracking_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
