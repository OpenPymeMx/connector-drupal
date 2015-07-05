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

import pytz

from datetime import datetime

from openerp.osv import orm, fields
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.translate import _

from openerp.addons.connector.unit.mapper import (
    ImportMapper, mapping, only_create
)
from openerp.addons.connector.exception import IDMissingInBackend

from .backend import drupal
from .unit.import_synchronizer import DrupalImportSynchronizer
from .unit.backend_adapter import DrupalCRUDAdapter


class res_partner(orm.Model):
    _inherit = 'res.partner'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.res.partner', 'openerp_id',
            string="Drupal Bindings"
        ),
        'drupal_address_bind_ids': fields.one2many(
            'drupal.address', 'openerp_id',
            string="Drupal Address Bindings"),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(res_partner, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_res_partner(orm.Model):
    _name = 'drupal.res.partner'
    _inherit = 'drupal.binding'
    _inherits = {'res.partner': 'openerp_id'}
    _description = 'Drupal Partner'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner', string='Partner', required=True,
            ondelete='cascade'
        ),
        'created_at': fields.datetime(
            'Created At (on Drupal)', readonly=True
        ),
        'updated_at': fields.datetime(
            'Updated At (on Drupal)', readonly=True
        ),
        'emailid': fields.char('E-mail address'),
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A partner with same ID on Drupal already exists for this website.'),
    ]


class drupal_address(orm.Model):
    _name = 'drupal.address'
    _inherit = 'drupal.binding'
    _inherits = {'res.partner': 'openerp_id'}
    _description = 'Drupal Address'

    _rec_name = 'backend_id'

    _columns = {
        'openerp_id': fields.many2one(
            'res.partner', string='Partner', required=True,
            ondelete='cascade'
        ),
        'created_at': fields.datetime(
            'Created At (on Drupal)', readonly=True
        ),
        'updated_at': fields.datetime(
            'Updated At (on Drupal)', readonly=True
        ),
        'is_billing': fields.boolean('Billing Address'),
        'is_shipping': fields.boolean('Shipping Address')
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A partner address with same ID on Drupal already exists.'),
    ]


@drupal
class PartnerImport(DrupalImportSynchronizer):
    """ Import a Drupal user as partner """
    _model_name = [
        'drupal.res.partner',
        'drupal.address'
    ]

    def run(self, drupal_id, force=False):
        """ Override default Drupal synchronization
        :param drupal_id: identifier of the record on Drupal
        """
        if not self.drupal_record:
            return DrupalImportSynchronizer.run(self, drupal_id, force)

        # If the record is already set because we are importing the data
        # from a sales order then skip Drupal request
        self.drupal_id = drupal_id

        skip = self._must_skip()
        if skip:
            return skip

        binding_id = self._get_binding_id()

        if not force and self._is_uptodate(binding_id):
            return _('Already up-to-date.')
        self._before_import()

        # import the missing linked resources
        self._import_dependencies()

        map_record = self._map_data()

        if binding_id:
            record = self._update_data(map_record)
            self._update(binding_id, record)
        else:
            record = self._create_data(map_record)
            binding_id = self._create(record)

        self.binder.bind(self.drupal_id, binding_id)

        self._after_import(binding_id)


@drupal
class PartnerImportMapper(ImportMapper):
    """ Map drupal users into res.partners """
    _model_name = 'drupal.res.partner'

    direct = [
        ('email', 'email'),
    ]

    @only_create
    @mapping
    def backend_id(self, record):
        """ Get backend for this record """
        return {'backend_id': self.backend_record.id}

    @only_create
    @mapping
    def created(self, record):
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
        # All openERP server fields must be on UTC timezone
        create = datetime.fromtimestamp(int(record['created']), pytz.UTC)
        return {
            'created_at': create.strftime(fmt)
        }

    @only_create
    @mapping
    def customer(self, record):
        return {'customer': True}

    @only_create
    @mapping
    def is_company(self, record):
        # partners are companies so we can bind
        # addresses on them
        return {'is_company': True}

    @only_create
    @mapping
    def openerp_id(self, record):
        """ Will bind the customer on a existing partner
        with the same email """
        sess = self.session
        partner_ids = sess.search(
            'res.partner',
            [('email', '=', record['mail']), ('customer', '=', True)]
        )
        if partner_ids:
            return {'openerp_id': partner_ids[0]}

    @mapping
    def updated(self, record):
        """ Update time when record updated on Drupal """
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
        # All openERP server fields must be on UTC timezone
        update = datetime.fromtimestamp(int(record['created']), pytz.UTC)
        return {
            'updated_at': update.strftime(fmt)
        }

    @mapping
    def names(self, record):
        # TODO: Refactor to map OpenERP res.partner to Drupal user
        address = record['commerce_customer_address']

        parts = [part for part in (address['first_name'],
                                   address['last_name']) if part]
        return {'name': ' '.join(parts)}

    @mapping
    def country(self, record):
        """ Get country from country code """
        address = record['commerce_customer_address']
        country_ids = self.session.search(
            'res.country', [('code', '=ilike', address['country'])]
        )
        return {'country_id': country_ids[0]}

    @mapping
    def state(self, record):
        """ Get state from administrative area code """
        address = record['commerce_customer_address']
        state_ids = self.session.search(
            'res.country.state',
            [('code', '=ilike', address['administrative_area'])]
        )
        return {'state_id': state_ids[0]}

    @mapping
    def city(self, record):
        """ Get city from data on record """
        address = record['commerce_customer_address']
        return {'city': address['locality']}

    @mapping
    def address(self, record):
        """ Get address from record """
        address = record['commerce_customer_address']
        return {'street': address['thoroughfare']}

    @mapping
    def zip(self, record):
        """ Get zip from data on record """
        address = record['commerce_customer_address']
        return {'zip': address['postal_code']}


@drupal
class PartnerImportAdapter(DrupalCRUDAdapter):
    """ Addapter for import Drupal users """
    _model_name = 'drupal.res.partner'
    _drupal_model = 'user'


@drupal
class AddressImportMapper(ImportMapper):
    _model_name = 'drupal.address'

    @only_create
    @mapping
    def backend_id(self, record):
        """ Get backend for this record """
        return {'backend_id': self.backend_record.id}

    @only_create
    @mapping
    def created(self, record):
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
        # All openERP server fields must be on UTC timezone
        create = datetime.fromtimestamp(int(record['created']), pytz.UTC)
        return {
            'created_at': create.strftime(fmt)
        }

    @mapping
    def updated(self, record):
        """ Update time when record updated on Drupal """
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
        # All openERP server fields must be on UTC timezone
        update = datetime.fromtimestamp(int(record['created']), pytz.UTC)
        return {
            'updated_at': update.strftime(fmt)
        }

    @mapping
    def names(self, record):
        # TODO: Refactor to map OpenERP res.partner to Drupal user
        address = record['commerce_customer_address']

        parts = [part for part in (address['first_name'],
                                   address['last_name']) if part]
        return {'name': ' '.join(parts)}

    @mapping
    def country(self, record):
        """ Get country from country code """
        address = record['commerce_customer_address']
        country_ids = self.session.search(
            'res.country', [('code', '=ilike', address['country'])]
        )
        return {'country_id': country_ids[0]}

    @mapping
    def state(self, record):
        """ Get state from administrative area code """
        address = record['commerce_customer_address']
        state_ids = self.session.search(
            'res.country.state',
            [('code', '=ilike', address['administrative_area'])]
        )
        return {'state_id': state_ids[0]}

    @mapping
    def city(self, record):
        """ Get city from data on record """
        address = record['commerce_customer_address']
        return {'city': address['locality']}

    @mapping
    def address(self, record):
        """ Get address from record """
        address = record['commerce_customer_address']
        return {'street': address['thoroughfare']}

    @mapping
    def zip(self, record):
        """ Get zip from data on record """
        address = record['commerce_customer_address']
        return {'zip': address['postal_code']}

    @mapping
    def type(self, record):
        if record.get('is_default_billing'):
            address_type = 'invoice'
        elif record.get('is_default_shipping'):
            address_type = 'delivery'
        else:
            address_type = 'contact'
        return {'type': address_type}
