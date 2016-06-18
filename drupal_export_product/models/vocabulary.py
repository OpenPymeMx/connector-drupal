# -*- coding: utf-8 -*-

from openerp.osv import orm, fields

from openerp.addons.connector.unit.mapper import ImportMapper, mapping

from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.binder import (
    DrupalModelBinder
)
from openerp.addons.connector_drupal_ecommerce.unit.import_synchronizer import (
    DirectBatchImport, DrupalImportSynchronizer
)
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import (
    DrupalCRUDAdapter
)


class drupal_vocabulary(orm.Model):
    """
    Class for store refencies to Drupal vocabularies
    """
    _name = 'drupal.vocabulary'
    _inherit = 'drupal.binding'
    _description = 'Drupal Vocabulary'

    _columns = {
        'name': fields.char('Name', required=True, readonly=True),
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A vocabulary with the same ID already exist')
    ]


@drupal
class DrupalVocabularyBinder(DrupalModelBinder):
    _model_name = 'drupal.vocabulary'


@drupal
class DrupalVocabularyMapper(ImportMapper):
    """ Map a Drupal vocabulary into OpenERP data """
    _model_name = 'drupal.vocabulary'

    direct = [('name', 'name'),
              ('vid', 'drupal_id')]

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


@drupal
class DrupalVocabularyBatchImport(DirectBatchImport):
    """
    Import Drupal Vocabulary into OpenERP
    """
    _model_name = 'drupal.vocabulary'


@drupal
class DrupalVocabularyBackendAdapter(DrupalCRUDAdapter):
    """
    CRUD adapter for Drupal Vocabulary
    """
    _model_name = 'drupal.vocabulary'
    _drupal_model = 'taxonomy_vocabulary'


@drupal
class DrupalVocabularyImport(DrupalImportSynchronizer):
    """ The actual class that save data from Drupal Vocabulary """
    _model_name = 'drupal.vocabulary'

    def run(self, drupal_id, force=False):
        """ Overrides the default synchronization because Drupal already
        sends all data on the index request, no need to request again
        :param drupal_id: the record fetched from Drupal
        """
        self.drupal_record = drupal_id
        self.drupal_id = drupal_id['vid']

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
