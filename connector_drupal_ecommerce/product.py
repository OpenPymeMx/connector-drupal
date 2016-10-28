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

from collections import defaultdict

from openerp.osv import orm, fields

from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.queue.job import job, related_action

from .backend import drupal
from .connector import get_environment
from .related_action import unwrap_binding
from .unit.export_synchronizer import DrupalExporter
from .unit.delete_synchronizer import DrupalDeleteSynchronizer
from .unit.backend_adapter import DrupalCRUDAdapter


class product_product(orm.Model):
    _inherit = 'product.product'

    def _get_checkpoint(self, cr, uid, ids, name, arg, context=None):
        result = {}
        checkpoint_obj = self.pool.get('connector.checkpoint')
        model_obj = self.pool.get('ir.model')
        model_id = model_obj.search(
            cr, uid,
            [('model', '=', 'product.product')],
            context=context
        )[0]
        for product_id in ids:
            point_ids = checkpoint_obj.search(
                cr, uid,
                [('model_id', '=', model_id),
                 ('record_id', '=', product_id),
                 ('state', '=', 'need_review')],
                context=context
            )
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
        return super(product_product, self).copy_data(
            cr, uid, id, default=default, context=context
        )


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
        'no_stock_sync': fields.boolean(
            'No Stock Synchronization', required=False,
            help="Check this to exclude the product "
                 "from stock synchronizations."
        ),
        'drupal_qty': fields.float(
            'Computed Quantity',
            help="Last computed quantity to send on Drupal."
        ),
    }

    _defaults = {
        'no_stock_sync': False,
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A product with same ID on Drupal already exists.'),
    ]

    def recompute_drupal_qty(self, cr, uid, ids, context=None):
        """ Check if the quantity in the stock location configured
        on the backend has changed since the last export.
        If it has changed, write the updated quantity on `drupal_qty`.
        The write on `drupal_qty` will trigger an `on_record_write`
        event that will create an export job.
        It groups the products by backend to avoid to read the backend
        informations for each product.
        """
        backend_obj = self.pool['drupal.backend']
        if not hasattr(ids, '__iter__'):
            ids = [ids]

        # group products by backend
        backends = defaultdict(list)
        products = self.read(
            cr, uid, ids, ['backend_id', 'drupal_qty'], context=context
        )
        for product in products:
            backends[product['backend_id'][0]].append(product)

        for backend_id, products in backends.iteritems():
            backend = backend_obj.browse(cr, uid, backend_id, context=context)
            self._recompute_drupal_qty_backend(
                cr, uid, backend, products, context=context
            )
        return True

    RECOMPUTE_QTY_STEP = 1000  # products at a time

    def _recompute_drupal_qty_backend(
        self, cr, uid, backend, products, read_fields=None, context=None
    ):
        """ Recompute the products quantity for one backend.
        If field names are passed in ``read_fields`` (as a list), they
        will be read in the product that is used in
        :meth:`~._drupal_qty`.
        """
        def chunks(items, length):
            for index in xrange(0, len(items), length):
                yield items[index:index + length]

        if context is None:
            context = {}

        if backend.product_stock_field_id:
            stock_field = backend.product_stock_field_id.name
        else:
            stock_field = 'virtual_available'

        location = backend.warehouse_id.lot_stock_id
        location_ctx = context.copy()
        location_ctx['location'] = location.id

        product_fields = ['drupal_qty', stock_field]
        if read_fields:
            product_fields += read_fields

        product_ids = [product['id'] for product in products]
        for chunk_ids in chunks(product_ids, self.RECOMPUTE_QTY_STEP):
            for product in self.read(
                cr, uid, chunk_ids, product_fields, context=location_ctx
            ):
                new_qty = self._drupal_qty(
                    cr, uid, product, backend, location, stock_field,
                    context=location_ctx
                )
                if new_qty != product['drupal_qty']:
                    self.write(
                        cr, uid, product['id'], {'drupal_qty': new_qty},
                        context=context
                    )

    def _drupal_qty(
        self, cr, uid, product, backend, location, stock_field, context=None
    ):
        """ Return the current quantity for one product.
        Can be inherited to change the way the quantity is computed,
        according to a backend / location.
        If you need to read additional fields on the product, see the
        ``read_fields`` argument of :meth:`~._recompute_magento_qty_backend`
        """
        return product[stock_field]


@drupal
class ProductInventoryExport(DrupalExporter):
    _model_name = ['drupal.product.product']
    _drupal_model = 'product'

    def _get_data(self, product, fields):
        return {'commerce_stock': product.drupal_qty}

    def run(self, binding_id, fields):
        """ Export the product inventory to Drupal """
        product = self.session.browse(self.model._name, binding_id)
        binder = self.get_binder_for_model()
        drupal_id = binder.to_backend(product.id)
        data = self._get_data(product, fields)
        # Only export inventory when product have been previus exported
        if drupal_id:
            self.backend_adapter.update_inventory(drupal_id, data)


@drupal
class ProductProductAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.product'
    _drupal_model = 'product'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['nid']

    def update_inventory(self, id, data):
        """ Write updated inventory on Drupal product """
        return self.write(id, data)


@drupal
class ProductProductDeleter(DrupalDeleteSynchronizer):
    _model_name = 'drupal.product.product'
    _drupal_model = 'product'


# fields which should not trigger an export of the products
# but an export of their inventory
INVENTORY_FIELDS = ('drupal_qty',)


@on_record_write(model_names='drupal.product.product')
def drupal_product_modified(session, model_name, record_id, vals):
    if session.context.get('connector_no_export'):
        return
    if session.browse(model_name, record_id).no_stock_sync:
        return
    inventory_fields = list(set(vals).intersection(INVENTORY_FIELDS))
    if inventory_fields:
        export_product_inventory(
            session, model_name, record_id, fields=inventory_fields
        )


@job
@related_action(action=unwrap_binding)
def export_product_inventory(session, model_name, record_id, fields=None):
    """ Export the inventory configuration and quantity of a product. """
    product = session.browse(model_name, record_id)
    backend_id = product.backend_id.id
    env = get_environment(session, model_name, backend_id)
    inventory_exporter = env.get_connector_unit(ProductInventoryExport)
    return inventory_exporter.run(record_id, fields)
