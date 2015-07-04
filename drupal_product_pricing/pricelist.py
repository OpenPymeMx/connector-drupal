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
from openerp.addons.connector_drupal_ecommerce.event import (
    on_product_price_changed
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
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        for record in self.browse(cr, uid, ids, context=context):
            session = ConnectorSession(cr, uid, context=context)
            binding_ids = record.backend_id.product_binding_ids
            for binding in binding_ids:
                product = binding.openerp_id
                product._check_price_items()
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
        self.binding_record.update_all_prices()


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

    def _check_price_items(self, cr, uid, ids, context=None):
        """ Check if all the needed drupal.product.priceitem objects exist
        and create all the records that needed """
        import collections
        for product in self.browse(cr, uid, ids, context=context):
            # Get all the existing price items ordered by backend
            existing = collections.defaultdict(list)
            for price_item in product.drupal_priceitem_ids:
                existing[price_item.backend_id.id].append(
                    price_item.pricelist_id.id
                )
            # Get all the missing price items
            missing = []
            for bind_record in product.drupal_bind_ids:
                backend = bind_record.backend_id
                for item in backend.drupal_pricelist_ids:
                    if item.id not in existing[backend.id]:
                        missing.append({
                            'openerp_id': product.id,
                            'pricelist_id': item.id,
                            'backend_id': backend.id,
                        })
            self.write(
                cr, uid, [product.id],
                {'drupal_priceitem_ids': [(0, 0, vals) for vals in missing]},
                context=context,
            )
            product.refresh()
        return

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
            product_ids = product_obj.search(
                cr, uid, [('product_tmpl_id', 'in', ids)], context=context
            )
            # when the write is done on the product.product, avoid
            # to fire the event 2 times
            if context.get('from_product_ids'):
                product_ids = list(set(product_ids) -
                                   set(context['from_product_ids']))
            for prod_id in product_ids:
                on_product_price_changed.fire(
                    session, product_obj._name, prod_id
                )

    def write(self, cr, uid, ids, vals, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        result = super(product_template, self).write(
            cr, uid, ids, vals, context=context
        )
        self._price_changed(cr, uid, ids, vals, context=context)
        return result


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
            # TODO: Drupal is using integer for store price amounts
            # the reason is documented here:
            # http://pixeljets.com/blog/storing-monetary-amounts-db-use-decimals-not-floats
            # we need to find a proper solution instead of the hardcoded *100
            'price_amount': price * 100,
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


@on_product_price_changed
def product_price_changed(session, model_name, record_id, fields=None):
    """ When a product.product price has been changed """
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get(model_name)
    record = model.browse(
        session.cr, session.uid, record_id, context=session.context
    )
    # Ensures all drupal binding needed for export price items already
    # exist before try to make the actual export
    record._check_price_items()
    for priceitem in record.drupal_priceitem_ids:
        export_product_price.delay(
            session, 'drupal.product.priceitem', priceitem.id
        )


@job
@related_action(action=unwrap_binding)
def export_product_price(session, model_name, record_id):
    """ Export the price of a product. """
    product_bind = session.browse(model_name, record_id)
    backend_id = product_bind.backend_id.id
    env = get_environment(session, model_name, backend_id)
    price_exporter = env.get_connector_unit(ProductPriceExporter)
    return price_exporter.run(record_id)
