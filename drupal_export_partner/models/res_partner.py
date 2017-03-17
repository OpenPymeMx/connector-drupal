# -*- coding: utf-8 -*-

from openerp.addons.connector.exception import InvalidDataError
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping,
)
from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.delete_synchronizer import (
    DrupalDeleteSynchronizer
)
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    DrupalExporter
)


@drupal
class ResPartnerExporter(DrupalExporter):
    _model_name = ['drupal.res.partner']

    def _validate_create_data(self, data):
        """ Check if the values to export are correct
        Pro-actively check before the ``Model.create`` if some fields
        are missing or invalid
        Raise `InvalidDataError`
        """
        if not data.get('mail'):
            raise InvalidDataError(
                'The partner does not have an email but it is mandatory '
                'for Drupal'
            )
        return

    def _validate_update_data(self, data):
        """ Check if the values to export are correct
        Pro-actively check before the ``Model.update`` if some fields
        are missing or invalid
        Raise `InvalidDataError`
        """
        if not data.get('mail'):
            raise InvalidDataError(
                'The partner does not have an email but it is mandatory '
                'for Drupal'
            )
        return


@drupal
class ResPartnerMapper(ExportMapper):
    _model_name = 'drupal.res.partner'

    direct = [
        ('email', 'name'),
        ('email', 'mail'),
    ]

    @mapping
    def default_values(self, record):
        return {
            'status': 1,
            'pass': 'disabled',
        }


@drupal
class ResPartnerDeleter(DrupalDeleteSynchronizer):
    _model_name = 'drupal.res.partner'
