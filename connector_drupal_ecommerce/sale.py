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

import logging

from openerp.osv import orm, fields
from openerp.tools.translate import _
from openerp.addons import decimal_precision as dp
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.mapper import (
    mapping, ImportMapper
)

from .backend import drupal
from .connector import get_environment
from .sale_order_onchange import SaleOrderOnChange
from .unit.import_synchronizer import (
    DrupalImportSynchronizer, DelayedBatchImport
)
from .unit.backend_adapter import DrupalCRUDAdapter

_logger = logging.getLogger(__name__)


class drupal_sale_order(orm.Model):
    _name = 'drupal.sale.order'
    _inherit = 'drupal.binding'
    _description = 'Drupal Sale Order'
    _inherits = {'sale.order': 'openerp_id'}

    _columns = {
        'openerp_id': fields.many2one(
            'sale.order', string='Sale Order', required=True,
            ondelete='cascade'
        ),
        'drupal_order_line_ids': fields.one2many(
            'drupal.sale.order.line', 'drupal_order_id',
            'Drupal Order Lines'
        ),
        # XXX common to all ecom sale orders
        'total_amount': fields.float(
            'Total amount',
            digits_compute=dp.get_precision('Account')
        ),
        # XXX common to all ecom sale orders
        'total_amount_tax': fields.float(
            'Total amount w. tax',
            digits_compute=dp.get_precision('Account')
        ),
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A sale order line with the same ID on Drupal already exists.'),
    ]


class sale_order(orm.Model):
    _inherit = 'sale.order'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.sale.order', 'openerp_id',
            string="Magento Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(sale_order, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_sale_order_line(orm.Model):
    _name = 'drupal.sale.order.line'
    _inherit = 'drupal.binding'
    _description = 'Drupal Sale Order Line'
    _inherits = {'sale.order.line': 'openerp_id'}

    def _get_lines_from_order(self, cr, uid, ids, context=None):
        return self.search(
            cr, uid, [('drupal_order_id', 'in', ids)], context=context
        )

    _columns = {
        'drupal_order_id': fields.many2one(
            'drupal.sale.order', 'Drupal Sale Order', required=True,
            ondelete='cascade', select=True
        ),
        'openerp_id': fields.many2one(
            'sale.order.line', string='Sale Order Line', required=True,
            ondelete='cascade'
        ),
        'backend_id': fields.related(
            'drupal_order_id', 'backend_id', type='many2one',
            relation='drupal.backend', string='Magento Backend',
            store={
                'drupal.sale.order.line':
                (lambda self, cr, uid, ids, c=None: ids,
                 ['drupal_order_id'], 10),
                'drupal.sale.order':
                (_get_lines_from_order, ['backend_id'], 20),
            },
            readonly=True
        ),
        'tax_rate': fields.float(
            'Tax Rate', digits_compute=dp.get_precision('Account')
        ),
        # XXX common to all ecom sale orders
        'notes': fields.char('Notes'),
        }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A sale order line with the same ID on Drupal already exists.'),
    ]

    def create(self, cr, uid, vals, context=None):
        drupal_order_id = vals['drupal_order_id']
        info = self.pool['drupal.sale.order'].read(
            cr, uid, [drupal_order_id], ['openerp_id'], context=context
        )
        order_id = info[0]['openerp_id']
        vals['order_id'] = order_id[0]
        return super(drupal_sale_order_line, self).create(
            cr, uid, vals, context=context
        )


class sale_order_line(orm.Model):
    _inherit = 'sale.order.line'
    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.sale.order.line', 'openerp_id',
            string="Drupal Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        if context is None:
            context = {}

        default['drupal_bind_ids'] = False
        return super(sale_order_line, self).copy_data(
            cr, uid, id, default=default, context=context
        )


@drupal
class SaleOrderBatchImport(DelayedBatchImport):
    _model_name = ['drupal.sale.order']

    def _import_record(self, record_id, **kwargs):
        """ Import the record directly """
        return super(SaleOrderBatchImport, self)._import_record(
            record_id,  # max_retries=0, priority=5
        )

    def run(self, filters=None):
        """ Run the synchronization """
        if filters is None:
            filters = {}
        filters['status'] = 'pending'
        from_date = filters.pop('from_date', None)
        # Current implementation of Drupal Commerce services doesn't
        # support range queries, not sure if later we are going to need
        # or the current implementation for us is good enought
        to_date = filters.pop('to_date', None)
        record_ids = self.backend_adapter.search(
            filters, from_date=from_date, to_date=to_date
        )
        _logger.info(
            'search for Drupal saleorders %s returned %s', filters, record_ids
        )
        for record_id in record_ids:
            self._import_record(record_id)


@drupal
class SaleOrderAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.sale.order'
    _drupal_model = 'order'

    def search(self, filters=None, from_date=None, to_date=None,):
        """ Manipulate from_date & to_date params to set filters """
        filters = filters or {}
        if from_date:
            filters['updated'] = self.totimestamp(from_date)
            filters['filter_op[updated]'] = '>='
        return DrupalCRUDAdapter.search(self, filters=filters)


@drupal
class SaleOrderImport(DrupalImportSynchronizer):
    _model_name = 'drupal.sale.order'

    def _must_skip(self):
        """ Hook called right after we read the data from the backend.
        If the method returns a message giving a reason for the
        skipping, the import will be interrupted and the message
        recorded in the job (if the import is called directly by the
        job, not by dependencies).
        If it returns None, the import will continue normally.
        :returns: None | str | unicode
        """
        if self.binder.to_openerp(self.drupal_id):
            return _('Already imported')

    def _import_customer(self):
        """
        Send the Drupal record on the importer to prevent asking again

        TODO: The Drupal addressbook allow users manage address on frontend
        by their own, we need to mimic the same functionality as much
        as possible on the backend.
        """
        session = self.session
        record = self.drupal_record
        billing_entities = record['commerce_customer_billing_entities']
        # Always map billing address to partner
        customer = billing_entities[record['commerce_customer_billing']]
        customer['mail'] = record['mail']

        importer_class = DrupalImportSynchronizer
        importer = self.get_connector_unit_for_model(
            importer_class, model='drupal.res.partner'
        )

        # Inject customer into importer object for prevent double request
        importer.drupal_record = customer
        importer.run(customer['uid'])

        partner_binder = self.get_binder_for_model('drupal.res.partner')
        partner_bind_id = partner_binder.to_openerp(customer['uid'])
        partner = session.browse(
            'drupal.res.partner', partner_bind_id
        ).openerp_id
        # Set partner for this order
        self.partner_id = partner.id

        # Import of shipping address.
        shipping_entities = record['commerce_customer_shipping_entities']
        # Always map billing address to partner
        shipping = shipping_entities[record['commerce_customer_shipping']]

        importer_class = DrupalImportSynchronizer
        importer = self.get_connector_unit_for_model(
            importer_class, model='drupal.address'
        )

        # Inject customer into importer object for prevent double request
        importer.drupal_record = shipping
        importer.run(shipping['profile_id'])

        address_binder = self.get_binder_for_model('drupal.address')
        address_bind_id = address_binder.to_openerp(shipping['profile_id'])
        address = session.browse(
            'drupal.address', address_bind_id
        ).openerp_id
        # Set partner for this order
        self.partner_shipping_id = address.id

    def _import_dependencies(self):
        """ Ensure all dependencies for sale order exist """
        record = self.drupal_record

        # Drupal Commerce Services module sends the customer information
        # on the same request than the order, we only need to save to OpenERP
        self._import_customer()

        for entity_id in record.get('commerce_line_items', []):
            entity = record['commerce_line_items_entities'][entity_id]
            _logger.debug('entity: %s', entity)
            if entity['type'] == 'product':
                self._import_dependency(
                    entity['commerce_product'], 'drupal.product.product'
                )

    def _create_data(self, map_record, **kwargs):
        """ Set partner information from record field """
        return super(SaleOrderImport, self)._create_data(
            map_record,
            partner_id=self.partner_id,
            partner_shipping_id=self.partner_shipping_id,
            **kwargs
        )

    def _update_data(self, map_record, **kwargs):
        """ Set partner information from record field """
        return super(SaleOrderImport, self)._update_data(
            map_record,
            partner_id=self.partner_id,
            partner_shipping_id=self.partner_shipping_id,
            **kwargs
        )


@drupal
class SaleOrderImportMapper(ImportMapper):
    _model_name = 'drupal.sale.order'

    def finalize(self, map_record, values):
        """
        For simplicity we are setting the partner_id, partner_shipping_id
        & partner_invoice_id in the importer this function added to the
        values dictionary
        """
        values.setdefault('order_line', [])
        values.update({
            'partner_id': self.options.partner_id,
            'partner_shipping_id': self.options.partner_shipping_id,
        })
        values['drupal_order_line_ids'] = []  # TODO: Remove with proper data
        # onchange = self.get_connector_unit_for_model(SaleOrderOnChange)
        # return onchange.play(values, values['drupal_order_line_ids'])
        return values

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def user_id(self, record):
        """ Do not assign to a Salesperson otherwise sales orders are hidden
        for the salespersons (access rules)"""
        return {'user_id': False}


@drupal
class DrupalSaleOrderOnChange(SaleOrderOnChange):
    _model_name = 'drupal.sale.order'


@job
def sale_order_import_batch(session, model_name, backend_id, filters=None):
    """ Prepare a batch import of records from Drupal """
    if filters is None:
        filters = {}
    env = get_environment(session, model_name, backend_id)
    importer = env.get_connector_unit(SaleOrderBatchImport)
    importer.run(filters)
