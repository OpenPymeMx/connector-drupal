# -*- coding: utf-8 -*-


{
    'name': 'Drupal Connector - Export Partners',
    'version': '1.0.0',
    'category': 'Drupal Connector',
    'author': "OpenPyme, Odoo Community Association (OCA)",
    'website': 'http://openerp-connector.com',
    'license': 'AGPL-3',
    'description': """
Drupal Connecto - Export Partners
=================================

Extension for **Drupal Connector**, export the partners to Drupal.

""",
    'depends': [
        'connector_drupal_ecommerce',
    ],
    'data': [
        'views/res_partner_view.xml',
        'wizard/export_partner.xml',
    ],
    'installable': True,
}
