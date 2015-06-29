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
###########################################################################

import logging

from datetime import datetime

from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT

from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import ImportSynchronizer
from openerp.addons.connector.exception import IDMissingInBackend
from openerp.addons.connector.connector import Environment

from ..connector import get_environment


_logger = logging.getLogger(__name__)


class DrupalImportSynchronizer(ImportSynchronizer):
    """ Base importer for Drupal """

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.Environment`
        """
        super(DrupalImportSynchronizer, self).__init__(environment)
        self.drupal_id = None
        self.drupal_record = None

    def _get_magento_data(self):
        """ Return the raw Drupal data for ``self.magento_id`` """
        return self.backend_adapter.read(self.drupal_id)

    def _before_import(self):
        """ Hook called before the import, when we have the Drupal
        data"""

    def _is_uptodate(self, binding_id):
        """Return True if the import should be skipped because
        it is already up-to-date in OpenERP"""
        assert self.drupal_record
        if not self.drupal_record.get('updated_at'):
            return  # no update date on Magento, always import it.
        if not binding_id:
            return  # it does not exist so it shoud not be skipped
        binding = self.session.browse(self.model._name, binding_id)
        sync = binding.sync_date
        if not sync:
            return
        fmt = DEFAULT_SERVER_DATETIME_FORMAT
        sync_date = datetime.strptime(sync, fmt)
        drupal_date = datetime.strptime(
            self.drupal_record['updated_at'], fmt
        )
        # if the last synchronization date is greater than the last
        # update in drupal, we skip the import.
        # Important: at the beginning of the exporters flows, we have to
        # check if the magento_date is more recent than the sync_date
        # and if so, schedule a new import. If we don't do that, we'll
        # miss changes done in Drupal
        return drupal_date < sync_date

    def _import_dependency(self, drupal_id, binding_model,
                           importer_class=None, always=False):
        """ Import a dependency.
        The importer class is a class or subclass of
        :class:`MagentoImportSynchronizer`. A specific class can be defined.
        :param magento_id: id of the related binding to import
        :param binding_model: name of the binding model for the relation
        :type binding_model: str | unicode
        :param importer_cls: :class:`openerp.addons.connector.\
                                     connector.ConnectorUnit`
                             class or parent class to use for the export.
                             By default: MagentoImportSynchronizer
        :type importer_cls: :class:`openerp.addons.connector.\
                                    connector.MetaConnectorUnit`
        :param always: if True, the record is updated even if it already
                       exists, note that it is still skipped if it has
                       not been modified on Magento since the last
                       update. When False, it will import it only when
                       it does not yet exist.
        :type always: boolean
        """
        if not drupal_id:
            return
        if importer_class is None:
            importer_class = DrupalImportSynchronizer
        binder = self.get_binder_for_model(binding_model)
        if always or binder.to_openerp(drupal_id) is None:
            importer = self.get_connector_unit_for_model(
                importer_class, model=binding_model)
            importer.run(drupal_id)

    def _import_dependencies(self):
        """ Import the dependencies for the record
        Import of dependencies can be done manually or by calling
        :meth:`_import_dependency` for each dependency.
        """
        return

    def _map_data(self):
        """ Returns an instance of
        :py:class:`~openerp.addons.connector.unit.mapper.MapRecord`
        """
        return self.mapper.map_record(self.drupal_record)

    def _validate_data(self, data):
        """ Check if the values to import are correct
        Pro-actively check before the ``_create`` or
        ``_update`` if some fields are missing or invalid.
        Raise `InvalidDataError`
        """
        return

    def _must_skip(self):
        """ Hook called right after we read the data from the backend.
        If the method returns a message giving a reason for the
        skipping, the import will be interrupted and the message
        recorded in the job (if the import is called directly by the
        job, not by dependencies).
        If it returns None, the import will continue normally.
        :returns: None | str | unicode
        """
        return

    def _get_binding_id(self):
        """Return the binding id from the drupal id"""
        return self.binder.to_openerp(self.drupal_id)

    def _create_data(self, map_record, **kwargs):
        return map_record.values(for_create=True, **kwargs)

    def _create(self, data):
        """ Create the OpenERP record """
        # special check on data before import
        self._validate_data(data)
        with self.session.change_context({'connector_no_export': True}):
            binding_id = self.session.create(self.model._name, data)
        _logger.debug('%s %d created from drupal %s',
                      self.model._name, binding_id, self.drupal_id)
        return binding_id

    def _update_data(self, map_record, **kwargs):
        return map_record.values(**kwargs)

    def _update(self, binding_id, data):
        """ Update an OpenERP record """
        # special check on data before import
        self._validate_data(data)
        with self.session.change_context({'connector_no_export': True}):
            self.session.write(self.model._name, binding_id, data)
        _logger.debug('%s %d updated from drupal %s',
                      self.model._name, binding_id, self.drupal_id)
        return

    def _after_import(self, binding_id):
        """ Hook called at the end of the import """
        return

    def run(self, drupal_id, force=False):
        """ Run the synchronization
        :param magento_id: identifier of the record on Magento
        """
        self.magento_id = drupal_id
        try:
            self.magento_record = self._get_magento_data()
        except IDMissingInBackend:
            return _('Record does no longer exist in Drupal')

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

        self.binder.bind(self.magento_id, binding_id)

        self._after_import(binding_id)


class BatchImportSynchronizer(ImportSynchronizer):
    """ The role of a BatchImportSynchronizer is to search for a list of
    items to import, then it can either import them directly or delay
    the import of each item separately.
    """

    def run(self, filters=None):
        """ Run the synchronization """
        record_ids = self.backend_adapter.search(filters)
        for record_id in record_ids:
            self._import_record(record_id)

    def _import_record(self, record_id):
        """ Import a record directly or delay the import of the record.
        Method to implement in sub-classes.
        """
        raise NotImplementedError


@job
def import_batch(session, model_name, backend_id, filters=None):
    """ Prepare a batch import of records from Drupal """
    env = get_environment(session, model_name, backend_id)
    importer = env.get_connector_unit(BatchImportSynchronizer)
    importer.run(filters=filters)


@job
def import_record(session, model_name, backend_id, drupal_id, force=False):
    """ Import a record from Drupal """
    env = get_environment(session, model_name, backend_id)
    importer = env.get_connector_unit(DrupalImportSynchronizer)
    importer.run(drupal_id, force=force)
