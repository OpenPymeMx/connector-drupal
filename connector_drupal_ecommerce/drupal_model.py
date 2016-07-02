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


class DrupalBackend(orm.Model):
    """
    Base class for Drupal Backend
    """
    _name = 'drupal.backend'
    _description = 'Drupal Backend'
    _inherit = 'connector.backend'
    _backend_type = 'drupal'

    def select_versions(self, cr, uid, context=None):
        """ Available versions in the backend.
        Can be inherited to add custom versions.  Using this method
        to add a version from an ``_inherit`` does not constrain
        to redefine the ``version`` field in the ``_inherit`` model.
        """
        return [('7', '7')]

    def _select_versions(self, cr, uid, context=None):
        """ Available versions in the backend.
        If you want to add a version, do not override this
        method, but ``select_version``.
        """
        return self.select_versions(cr, uid, context=context)

    def _select_timezones(self, cr, uid, context=None):
        """ List all the available timezones"""
        import pytz
        timezones = []
        for tz in pytz.all_timezones:
            timezones.append((tz, tz))
        return timezones

    def _get_stock_field_id(self, cr, uid, context=None):
        """ Set default stock field to virtual available """
        field_ids = self.pool.get('ir.model.fields').search(
            cr, uid,
            [('model', '=', 'product.product'),
             ('name', '=', 'virtual_available')],
            context=context
        )
        return field_ids[0]

    _columns = {
        'version': fields.selection(
            _select_versions, string='Version', required=True
        ),
        'url': fields.char(
            'Drupal URL', required=True,
            help='Url to Drupal token session, usually something like'
            'http://yourdomain.com'
        ),
        'endpoint': fields.char(
            'Location', required=True,
            help="Drupal end point whre Drupal services module is listening"
        ),
        'username': fields.char(
            'Username', help="Webservice user"
        ),
        'password': fields.char(
            'Password', help="Webservice password"
        ),
        'timeout': fields.integer(
            'Timeout', help="Timeout for rest connections with Drupal backend"
        ),
        'default_lang_id': fields.many2one(
            'res.lang', 'Default Drupal Language',
            help="If a default language is selected, the records "
                 "will be imported in the translation of this language.\n"
                 "Note that a similar configuration exists "
                 "for each storeview."
        ),
        'default_timezone': fields.selection(
            _select_timezones,
            string='Default Drupal Timezone',
            help='If no default timezone is selected, the records '
            'could be not correctly sync with Drupal'
        ),
        'warehouse_id': fields.many2one(
            'stock.warehouse', 'Warehouse', required=True,
            help='Warehouse used to compute the stock quantities.'
        ),
        'product_stock_field_id': fields.many2one(
            'ir.model.fields', string='Stock Field',
            domain="[('model', 'in', ['product.product', 'product.template']),"
                   " ('ttype', '=', 'float')]",
            help="Choose the field of the product which will be used for "
                 "stock inventory updates.\nIf empty, Quantity Available "
                 "is used."
        ),
        'product_binding_ids': fields.one2many(
            'drupal.product.product', 'backend_id', string='Drupal Products',
            readonly=True
        ),
    }

    _defaults = {
        'timeout': 1,
        'product_stock_field_id': _get_stock_field_id,
    }

    def test_backend(self, cr, uid, ids, context=None):
        """
        Test connection with selected Drupal backend
        """
        from .unit.backend_adapter import DrupalServices

        for backend in self.browse(cr, uid, ids, context=context):
            drupal = DrupalServices(
                {'base_url': backend.url,
                 'endpoint': backend.endpoint,
                 'username': backend.username,
                 'password': backend.password,
                 'timeout':  backend.timeout}
            )
            drupal.user_login()
        try:
            pass
            # DrupalServices(config)
        except Exception, e:
            raise orm.except_orm(
                _('Error'),
                e
            )
        finally:
            raise orm.except_orm(
                _('Correct'),
                _('Everything seems correct')
            )

    def _domain_for_update_product_stock_qty(self, cr, uid, ids, context=None):
        return [
            ('backend_id', 'in', ids),
            ('type', '!=', 'service'),
            ('no_stock_sync', '=', False),
        ]

    def update_product_stock_qty(self, cr, uid, ids, context=None):
        if not hasattr(ids, '__iter__'):
            ids = [ids]
        drupal_product_obj = self.pool.get('drupal.product.product')
        domain = self._domain_for_update_product_stock_qty(
            cr, uid, ids, context=context
        )
        product_ids = drupal_product_obj.search(
            cr, uid, domain, context=context
        )
        drupal_product_obj.recompute_drupal_qty(
            cr, uid, product_ids, context=context
        )
        return True

    def _drupal_backend(self, cr, uid, callback, domain=None, context=None):
        if domain is None:
            domain = []
        ids = self.search(cr, uid, domain, context=context)
        if ids:
            callback(cr, uid, ids, context=context)

    def _scheduler_update_product_stock_qty(
        self, cr, uid, domain=None, context=None
    ):
        self._drupal_backend(
            cr, uid, self.update_product_stock_qty, domain=domain,
            context=context
        )
