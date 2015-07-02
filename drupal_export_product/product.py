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
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)

from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.event import (
    on_product_price_changed
)
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import DrupalExporter
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import DrupalCRUDAdapter


class drupal_backend(orm.Model):
    """ Add relation to drupal.product.product object on backend """
    _inherit = 'drupal.backend'
    _columns = {
        'product_binding_ids': fields.one2many(
            'drupal.product.product', 'backend_id', string='Drupal Products',
            readonly=True
        ),
    }


class product_template(orm.Model):
    _inherit = 'product.template'

    # TODO implement set function and also support multi tax
    def _price_changed(self, cr, uid, ids, vals, context=None):
        """ Fire the ``on_product_price_changed`` on all the variants of
        the template if the price if the product could have changed.

        If one of the field used in a sale pricelist item has been
        modified, we consider that the price could have changed.

        There is no guarantee that's the price actually changed,
        because it depends on the pricelists.
        """
        if context is None:
            context = {}
        type_obj = self.pool['product.price.type']
        price_fields = type_obj.sale_price_fields(cr, uid, context=context)
        # restrict the fields to the template ones only, so if
        # the write has been done on product.product, we won't
        # update all the variant if a price field of the
        # variant has been changed
        tmpl_fields = [field for field in vals if field in self._columns]
        if any(field in price_fields for field in tmpl_fields):
            product_obj = self.pool['product.product']
            session = ConnectorSession(cr, uid, context=context)
            product_ids = product_obj.search(cr, uid,
                                             [('product_tmpl_id', 'in', ids)],
                                             context=context)
            # when the write is done on the product.product, avoid
            # to fire the event 2 times
            if context.get('from_product_ids'):
                product_ids = list(set(product_ids) -
                                   set(context['from_product_ids']))
            for prod_id in product_ids:
                on_product_price_changed.fire(session,
                                              product_obj._name,
                                              prod_id)

    def write(self, cr, uid, ids, vals, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        result = super(product_template, self).write(cr, uid, ids,
                                                     vals, context=context)
        self._price_changed(cr, uid, ids, vals, context=context)
        return result


class product_product(orm.Model):
    _inherit = 'product.product'

    def _get_checkpoint(self, cr, uid, ids, name, arg, context=None):
        result = {}
        checkpoint_obj = self.pool.get('connector.checkpoint')
        model_obj = self.pool.get('ir.model')
        model_id = model_obj.search(cr, uid,
                                    [('model', '=', 'product.product')],
                                    context=context)[0]
        for product_id in ids:
            point_ids = checkpoint_obj.search(cr, uid,
                                              [('model_id', '=', model_id),
                                               ('record_id', '=', product_id),
                                               ('state', '=', 'need_review')],
                                              context=context)
            result[product_id] = bool(point_ids)
        return result

    _columns = {
        'has_checkpoint': fields.function(
            _get_checkpoint, type='boolean', readonly=True,
            string='Has Checkpoint'
        ),
        'drupal_bind_ids': fields.one2many(
            'drupal.product.product', 'openerp_id',
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

    def _price_changed(self, cr, uid, ids, vals, context=None):
        """ Fire the ``on_product_price_changed`` if the price
        if the product could have changed.

        If one of the field used in a sale pricelist item has been
        modified, we consider that the price could have changed.

        There is no guarantee that's the price actually changed,
        because it depends on the pricelists.
        """
        type_obj = self.pool['product.price.type']
        price_fields = type_obj.sale_price_fields(cr, uid, context=context)
        if any(field in price_fields for field in vals):
            session = ConnectorSession(cr, uid, context=context)
            for prod_id in ids:
                on_product_price_changed.fire(session, self._name, prod_id)

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        context = context.copy()
        context['from_product_ids'] = ids
        result = super(product_product, self).write(
            cr, uid, ids, vals, context=context
        )
        self._price_changed(cr, uid, ids, vals, context=context)
        return result

    def create(self, cr, uid, vals, context=None):
        product_ids = super(product_product, self).create(
            cr, uid, vals, context=context
        )
        self._price_changed(cr, uid, [product_ids], vals, context=context)
        return product_ids


class drupal_product_product(orm.Model):
    _name = 'drupal.product.product'
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
class ProductProductExport(DrupalExporter):
    _model_name = ['drupal.product.product']

    def _export_dependencies(self):
        """ Export dependencies for the record """
        self._export_dependency(
            self.binding_record.openerp_id.categ_id,
            'drupal.product.category', exporter_class=ProductCategoryExport
        )


@drupal
class ProductProductMapper(ExportMapper):
    _model_name = 'drupal.product.product'

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
class ProductProductAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.product'
    _drupal_model = 'node'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['nid']


class product_price_type(orm.Model):
    _inherit = 'product.price.type'

    _columns = {
        'pricelist_item_ids': fields.one2many(
            'product.pricelist.item', 'base',
            string='Pricelist Items',
            readonly=True)
    }

    def sale_price_fields(self, cr, uid, context=None):
        """ Returns a list of fields used by sale pricelists.
        Used to know if the sale price could have changed
        when one of these fields has changed.
        """
        item_obj = self.pool['product.pricelist.item']
        item_ids = item_obj.search(
            cr, uid,
            [('price_version_id.pricelist_id.type', '=', 'sale')],
            context=context
        )
        type_ids = self.search(
            cr, uid,
            [('pricelist_item_ids', 'in', item_ids)],
            context=context
        )
        types = self.read(cr, uid, type_ids, ['field'], context=context)
        return [t['field'] for t in types]


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
