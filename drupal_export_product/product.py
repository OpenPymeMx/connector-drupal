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


from openerp.osv import orm, fields

from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector.exception import InvalidDataError
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)

from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import DrupalExporter
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import DrupalCRUDAdapter


class product_product(orm.Model):
    _inherit = 'product.product'

    _columns = {
        'drupal_node_bind_ids': fields.one2many(
            'drupal.product.node', 'openerp_id',
            string="Drupal Node Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_node_bind_ids'] = False
        return super(product_product, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_product_node(orm.Model):
    _name = 'drupal.product.node'
    _inherit = 'drupal.binding'
    _inherits = {'product.product': 'openerp_id'}
    _description = 'Drupal Product'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'product.product', string='Product',
            required=True, ondelete='cascade'
        ),
        'created_at': fields.datetime(
            'Created At (on Drupal)', readonly=True
        ),
        'updated_at': fields.datetime(
            'Updated At (on Drupal)', readonly=True
        ),
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A product with same ID on Drupal already exists.'),
    ]


@drupal
class ProductNodeExport(DrupalExporter):
    _model_name = ['drupal.product.node']

    def _export_dependencies(self):
        """ Export dependencies for the record """
        self._export_dependency(
            self.binding_record.openerp_id.categ_id,
            'drupal.product.category', exporter_class=ProductCategoryExport
        )

    def _validate_create_data(self, data):
        """ Check that is set Code on OpenERP product as we are exporting
        to SKU field on Drupal that is master data for commerce
        Raise `InvalidDataError`
        """
        data_product = data['field_product']['und']['form']
        if not data_product['sku']:
            raise InvalidDataError(
                'The product does not have Code but is mandatory for Drupal'
            )
        return

    def _after_export(self):
        """ After export we need to create the drupal.product.product
        object for being able to export stock levels
        TODO: Refactor as a dependency and stop using commerce_kickstart
        """
        record = self.backend_adapter.read(self.drupal_id)
        d_product_obj = self.session.pool.get('drupal.product.product')
        d_product_obj.create(
            self.session.cr, self.session.uid,
            {'openerp_id': self.binding_record.openerp_id.id,
             'drupal_id': record['field_product']['und'][0]['product_id'],
             'backend_id': self.binding_record.backend_id.id},
            context=self.session.context
        )
        return


@drupal
class ProductNodeMapper(ExportMapper):
    _model_name = 'drupal.product.node'

    direct = [
        ('name', 'title'),
    ]

    @mapping
    def commerce_field_product(self, record):
        """ Get price for current product """
        # TODO: Refactor and find a better way to handle Drupal fields
        product = record.openerp_id

        field_product = {}
        field_product['und'] = {}
        field_product['und']['form'] = {
            'commerce_price': {
                'und': [{
                    'amount': product.list_price * 100,
                    'currency_code': product.company_id.currency_id.name,
                }]
            },
            'title_field': product.name,
            'sku': product.code
        }

        categories = []
        for taxonomy in product.categ_id.drupal_bind_ids:
            categories.append({'tid': taxonomy.drupal_id})

        return {
            'type': 'product_display',
            'title_field': {'und': [{'value': product.name}]},
            'body': {'und': [{'value': product.description}]},
            'field_product': field_product,
            'field_product_category': {'und': categories[0]}
        }


@drupal
class ProductNodeAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.node'
    _drupal_model = 'node'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['nid']


class product_category(orm.Model):
    _inherit = 'product.category'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.product.category', 'openerp_id',
            string="Drupal Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(product_category, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_product_category(orm.Model):
    _name = 'drupal.product.category'
    _inherit = 'drupal.binding'
    _inherits = {'product.category': 'openerp_id'}
    _description = 'Drupal Product Category'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'product.category', string='Product Category',
            required=True, ondelete='cascade'
        ),
        'created_at': fields.datetime(
            'Created At (on Drupal)', readonly=True
        ),
        'updated_at': fields.datetime(
            'Updated At (on Drupal)', readonly=True
        ),
        # TODO:Find a way to let the user select the vocabulary to sinc
        'vid': fields.integer(
            'Drupal Vocabulary id', required=True, readonly=True
        )
    }

    _defauls = {
        'vid': 1
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A taxonomy with same ID on Drupal already exists.'),
    ]


@drupal
class ProductCategoryExport(DrupalExporter):
    _model_name = ['drupal.product.category']


@drupal
class ProductCategoryExportMapper(ExportMapper):
    _model_name = 'drupal.product.category'

    direct = [
        ('name', 'name'),
        ('vid', 'vid'),
    ]


@drupal
class ProductCategoryAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.category'
    _drupal_model = 'taxonomy_term'

    def create(self, data):
        """ Override method to extract id for new record"""
        result = super(ProductCategoryAdapter, self).create(data)
        # for some reason result is a list. so we retrieve the first item.
        return result['tid']
