# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright 2015 OpenPyme México
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'name': 'Drupal Connector - Pricing',
    'version': '1.0.0',
    'category': 'Connector',
    'depends': [
        'connector_drupal_ecommerce',
    ],
    'author': "OpenPyme,Odoo Community Association (OCA)",
    'license': 'AGPL-3',
    'website': 'http://www.openpyme.mx',
    'description': """
Drupal Connector - Pricing
==========================

Extension for **Drupal Connector**.

The prices of the products are managed in OpenERP using pricelists and
are pushed to Drupal.
    """,
    'images': [],
    'demo': [],
    'data': [
        'wizard/export_pricelist.xml',
        'views/pricelist_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
}
