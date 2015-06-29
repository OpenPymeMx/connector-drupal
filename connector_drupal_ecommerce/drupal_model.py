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
from openerp.tools import SUPERUSER_ID

from openerp.addons.connector.session import ConnectorSession

from .unit.export_synchronizer import export_record


class DrupalDomains(orm.Model):
    """
    Class for set Domains for information sync with Drupal
    """
    _name = 'drupal.domain'
    _description = 'Domain for limit objects sync with Drupal'

    _columns = {
        'object': fields.many2one(
            'ir.model', 'Model',
            required=True, help='Object to limit',
        ),
        'domain': fields.char(
            'Domain', required=True,
            help='Domain for limit the objects sync with Drupal'
        ),
        'backend': fields.many2one(
            'drupal.backend', 'Backend', required=True
        )
    }


class DrupalBackend(orm.Model):
    """
    Base class for Drupal Backend
    """
    _name = 'drupal.backend'
    _description = 'Drupal Backend'
    _inherit = 'connector.backend'
    _backend_type = 'drupal'

    def _select_versions(self, cr, uid, context=None):
        """ Available versions in the backend.
        Can be inherited to add custom versions.  Using this method
        to add a version from an ``_inherit`` does not constrain
        to redefine the ``version`` field in the ``_inherit`` model.
        """
        return [('7', '7')]

    def _select_timezones(self, cr, uid, context=None):
        """ List all the available timezones"""
        import pytz
        timezones = []
        for tz in pytz.all_timezones:
            timezones.append((tz, tz))
        return timezones

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
        'domains': fields.one2many(
            'drupal.domain', 'backend',
            'Domains', help='Create one line for every object'
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
        )
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
                 'password': backend.password}
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

    def sync_product_categories(self, cr, uid, ids, context=None):
        """
        Create a job for sync product categories with Drupal Commerce
        TODO: Currently only supports export categories from OpenERP to Drupal
        """
        context = context or {}
        product_category = self.pool.get('product.category')
        session = ConnectorSession(cr, uid, context=context)
        field_list = ['name', 'parent_id', 'sequence', 'vid']

        for backend in self.browse(cr, uid, ids, context=context):
            for domain in backend.domains:
                if not domain.object.model == 'product.category':
                    continue
                domain = eval("[%s]" % domain.domain)

        record_ids = product_category.search(
            cr, SUPERUSER_ID, domain, context=context
        )

        for record in product_category.browse(
            cr, SUPERUSER_ID, record_ids, context=context
        ):
            for binding in record.drupal_bind_ids:
                export_record.delay(
                    session, binding._model._name, binding.id,
                    fields=field_list
                )
        return

    def export_products(self, cr, uid, ids, context=None):
        """
        Create a job for sync product with Drupal Commerce
        TODO: Currently only supports export products from OpenERP to Drupal
        """
        context = context or {}
        product_obj = self.pool.get('product.product')
        session = ConnectorSession(cr, uid, context=context)

        for backend in self.browse(cr, uid, ids, context=context):
            for domain in backend.domains:
                if not domain.object.model == 'product.product':
                    continue
                domain = eval("[%s]" % domain.domain)

        record_ids = product_obj.search(
            cr, SUPERUSER_ID, domain, context=context
        )

        for record in product_obj.browse(
            cr, SUPERUSER_ID, record_ids, context=context
        ):
            # If there is no binding object created yet then we create
            if not len(record.drupal_bind_ids):
                vals = {
                    'openerp_id': record.id,
                    'backend_id': backend.id
                }
                product_obj.write(
                    cr, uid, record.id,
                    {'drupal_bind_ids': [(0, 0, vals)]},
                    context=context
                )
                record.refresh()
            for binding in record.drupal_bind_ids:
                export_record.delay(
                    session, binding._model._name, binding.id
                )
        return
