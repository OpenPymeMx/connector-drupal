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

from openerp.osv import orm, fields

from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector.queue.job import job, related_action
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)
from openerp.addons.connector_drupal_ecommerce.connector import (
    get_environment
)
from openerp.addons.connector_drupal_ecommerce.related_action import (
    unwrap_binding
)
from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    DrupalExporter
)
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import (
    DrupalCRUDAdapter
)


class pricelist(orm.Model):
    _inherit = 'product.pricelist'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.product.pricelist', 'openerp_id',
            string="Drupal Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(pricelist, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_product_pricelist(orm.Model):
    _name = 'drupal.product.pricelist'
    _inherit = 'drupal.binding'
    _inherits = {'product.pricelist': 'openerp_id'}
    _description = 'Drupal Pricelist'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'product.pricelist', string='Product Pricelist',
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
         'A pricelist with same ID on Drupal already exists.'),
    ]

    def update_all_prices(self, cr, uid, ids, context=None):
        """ Update the prices of all the products linked to the
        website. """
        product_ob = self.pool.get('product.product')
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        for record in self.browse(cr, uid, ids, context=context):
            session = ConnectorSession(cr, uid, context=context)
            binding_ids = record.backend_id.product_binding_ids
            for binding in binding_ids:
                product = binding.openerp_id
                if not len(product.drupal_priceitem_ids):
                    # No priceitem binding create first
                    vals = {
                        'openerp_id': product.id,
                        'pricelist_id': record.id,
                        'backend_id': record.backend_id.id,
                    }
                    product_ob.write(
                        cr, uid, [product.id],
                        {'drupal_priceitem_ids': [(0, 0, vals)]},
                        context=context,
                    )
                    product.refresh()
                for priceitem in product.drupal_priceitem_ids:
                    if priceitem.pricelist_id.id == record.id:
                        export_product_price.delay(
                            session, 'drupal.product.priceitem', priceitem.id
                        )


@drupal
class ProductPricelistExport(DrupalExporter):
    _model_name = ['drupal.product.pricelist']

    def _after_export(self):
        """
        After export pricelist we need to create a price item for every
        product exported from OpenERP for current pricelist
        """
        pass


@drupal
class ProductPricelistMapper(ExportMapper):
    _model_name = 'drupal.product.pricelist'

    direct = [
        ('name', 'title'),
        ('active', 'status')
    ]


@drupal
class ProductPricelistAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.pricelist'
    _drupal_model = 'pricelist'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['list_id']


class product_product(orm.Model):
    _inherit = 'product.product'

    _columns = {
        'drupal_priceitem_ids': fields.one2many(
            'drupal.product.priceitem', 'openerp_id',
            string="Drupal Priceitem Bindings"
        ),
    }


class drupal_product_priceitem(orm.Model):
    _name = 'drupal.product.priceitem'
    _inherit = 'drupal.binding'
    _inherits = {'product.product': 'openerp_id'}
    _description = 'Drupal Priceitem'

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
        'pricelist_id': fields.many2one(
            'drupal.product.pricelist', string='Drupal pricelist'
        ),
    }

    _sql_constraints = [
        ('priceitem_uniq', 'unique(openerp_id, backend_id, pricelist_id)',
         'A price item for same product and pricelist already exist')
    ]

    def _get_price(self, cr, uid, ids, context=None):
        """ Return the raw OpenERP data for ``self.binding_id`` """
        record = self.browse(cr, uid, ids, context=context)[0]
        return record.openerp_id.price


@drupal
class ProductPriceExporter(DrupalExporter):
    """ Export the price of a product.
    Use the pricelist configured on the backend for the
    default price in Drupal.
    """
    _model_name = ['drupal.product.priceitem']


@drupal
class ProductPriceitemMapper(ExportMapper):
    _model_name = 'drupal.product.priceitem'

    direct = [
        ('active', 'status'),
    ]

    @mapping
    def get_price(self, record):
        pricelist = record.pricelist_id.openerp_id
        context = {'pricelist': pricelist.id}
        price = record._get_price(context=context)
        return {
            'price_amount': price,
            'currency_code': pricelist.currency_id.name
        }

    @mapping
    def get_sku(self, record):
        return {'sku': record.openerp_id.code}

    @mapping
    def get_pricelist_id(self, record):
        return {'pricelist_id': record.pricelist_id.drupal_id}


@drupal
class ProductPriceitemAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.priceitem'
    _drupal_model = 'priceitem'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['item_id']

    def write(self, id, data):
        """ Update the record on Drupal adds the
        item_id to payload in order to prevent errors with
        Services entities """
        data['item_id'] = id
        return self._call('/'.join([self._drupal_model, id]), data, 'put')


@job
@related_action(action=unwrap_binding)
def export_product_price(session, model_name, record_id):
    """ Export the price of a product. """
    product_bind = session.browse(model_name, record_id)
    backend_id = product_bind.backend_id.id
    env = get_environment(session, model_name, backend_id)
    price_exporter = env.get_connector_unit(ProductPriceExporter)
    return price_exporter.run(record_id)
