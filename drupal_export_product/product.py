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
from openerp.tools.translate import _

from openerp.addons.connector.exception import InvalidDataError
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)

from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    DrupalExporter
)
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import (
    DrupalCRUDAdapter
)


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
            'drupal.product.category', exporter_class=ProductCategoryExport,
        )

    def _validate_create_data(self, data):
        """ Check that is set Code on OpenERP product as we are exporting
        to SKU field on Drupal that is master data for commerce
        Raise `InvalidDataError`
        """
        data_product = data['field_product']['und']['form']
        if not data_product['sku']:
            raise InvalidDataError(
                _('The product does not have Code but is mandatory for Drupal')
            )
        return

    def _after_export(self):
        """ After export we need to create the drupal.product.product
        object for being able to export stock levels
        TODO: Refactor as a dependency and stop using commerce_kickstart
              so we could create drupal product first and send as a
              related field to product_display nodes instead of being
              forced to always send product & display nodes at same time
        """
        if len(self.binding_record.drupal_bind_ids) < 1:
            # The drupal.product.product only needs to be created first time
            # product is exported to Drupal
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
                    'amount': product.list_price,
                    'currency_code': product.company_id.currency_id.name,
                }]
            },
            'title_field': product.name,
            'sku': product.code,
            'field_images': [{
                'fid': 0
            }],
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
        'vid': fields.related(
            'backend_id', 'drupal_vocabulary_id', 'drupal_id',
            type='integer', relation='drupal.vocabulary',
            string='Drupal Vocabulary', store=True
        )
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A taxonomy with same ID on Drupal already exists.'),
    ]

    def _check_main_category(self, cr, uid, ids, context=None):
        """
        Check the binded record is not the same mapped with Drupal Vocabulary
        """
        context = context or {}
        record = self.browse(cr, uid, ids, context=context)[0]
        backend = record.backend_id
        if record.openerp_id.id == backend.main_product_category_id.id:
            return True
        return False

    _constraint = [
        (_check_main_category,
         _('You cannot export category mapped to Drupal Vocabulary'),
         ['vid'])
    ]


@drupal
class ProductCategoryExport(DrupalExporter):
    _model_name = ['drupal.product.category']

    def _export_dependencies(self):
        """ Export the parent category for the record"""
        backend = self.backend_record
        category = self.binding_record.openerp_id

        # Parent category is mapped to Drupal vocabulary, do not export it
        is_main = category.parent_id.id == backend.main_product_category_id.id
        if is_main:
            return

        self._export_dependency(
            self.binding_record.openerp_id.parent_id,
            'drupal.product.category', exporter_class=ProductCategoryExport,
        )


@drupal
class ProductCategoryExportMapper(ExportMapper):
    _model_name = 'drupal.product.category'

    direct = [
        ('name', 'name'),
        ('vid', 'vid'),
    ]

    @mapping
    def parent_category(self, record):
        """
        Get parent category in order to export the hierarchy categories
        created on OpenERP to Drupal
        """
        parent_id = None
        category = record.openerp_id
        backend = record.backend_id

        # Does the parent category is the category mapped to Vocabulary?
        is_main = category.parent_id.id == backend.main_product_category_id.id

        if category.parent_id and not is_main:
            parent_id = category.parent_id.drupal_bind_ids[0].drupal_id

        return {'parent': parent_id}


@drupal
class ProductCategoryAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.category'
    _drupal_model = 'taxonomy_term'

    def create(self, data):
        """ Override method to extract id for new record"""
        result = super(ProductCategoryAdapter, self).create(data)
        # for some reason result is a list. so we retrieve the first item.
        return result['tid']

    def write(self, id, data):
        """ Override method to add id for record into data """
        data['tid']=id
        return DrupalCRUDAdapter.write(self, id, data)
