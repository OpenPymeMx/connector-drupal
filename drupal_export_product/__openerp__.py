# -*- coding: utf-8 -*-
###########################################################################
#    Module Writen to OpenERP, Open Source Management Solution
#
#    Copyright (c) 2015 OpenPyme - http://www.openpyme.mx/
#    All Rights Reserved.
#    Coded by: Agustín Cruz (agustin.cruz@openpyme.mx)
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

{'name': 'Connector for Drupal Ecommerce',
 'version': '1.0',
 'category': 'Connector',
 'author': "OpenPyme, Odoo Community Association (OCA)",
 'website': 'http://openerp-connector.com',
 'license': 'AGPL-3',
 'description': """
Connector for Drupal E-Commerce
===============================

This modules aims to be a common layer for the connectors dealing with
Drupal e-commerce.

That's a technical module, which include amongst other things:

Events

    On which the connectors can subscribe consumers
    (tracking number added, invoice paid, picking sent, ...)


ConnectorUnit

    A piece of code which allows to play all the ``onchanges`` required
    when we create a sale order.

Data Model

    Add structures shared for e-commerce connectors


 .. _`connector`: http://openerp-connector.com
.. _`magentoerpconnect`: http://openerp-magento-connector.com
.. _`prestashoperpconnect`: https://launchpad.net/prestashoperpconnect
""",
 'depends': [
    'product',
    'stock',
    'connector_drupal_ecommerce',
 ],
 'data': [
    'views/product_view.xml',
    'wizard/export_product.xml',
    'security/ir.model.access.csv',
 ],
 'installable': True,
 }
