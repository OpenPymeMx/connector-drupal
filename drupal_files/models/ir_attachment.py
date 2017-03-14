# -*- coding: utf-8 -*-

import logging

from openerp.osv import fields, orm

from openerp.addons.connector.exception import IDMissingInBackend
from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)
from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    DrupalExporter
)
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import (
    DrupalCRUDAdapter
)
from openerp.addons.connector_drupal_ecommerce.unit.binder import (
    DrupalModelBinder
)
from openerp.addons.connector_drupal_ecommerce.unit.delete_synchronizer import (
    DrupalDeleteSynchronizer, export_delete_record
)


_logger = logging.getLogger(__name__)


class ir_attachment(orm.Model):
    _inherit = 'ir.attachment'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.file', 'openerp_id',
            string="Drupal Node Bindings"
        ),
    }

    def copy(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(ir_attachment, self).copy(
            cr, uid, id, default=default, context=context
        )

    def unlink(self, cr, uid, ids, context=None):
        session = ConnectorSession(cr, uid, context=context)
        for record in self.browse(cr, uid, ids, context=context):
            if record.drupal_bind_ids:
                for backend in record.drupal_bind_ids:
                    export_delete_record.delay(
                        session, 'drupal.file', backend.backend_id.id,
                        backend.drupal_id
                    )
        return super(ir_attachment, self).unlink(
            cr, uid, ids, context=context
        )


class drupal_file(orm.Model):
    _name = 'drupal.file'
    _inherit = 'drupal.binding'
    _inherits = {'ir.attachment': 'openerp_id'}
    _description = 'Drupal File'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'ir.attachment', string='Attachment',
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
         'A file with same ID on Drupal already exists.'),
    ]


@drupal
class FileExport(DrupalExporter):
    _model_name = ['drupal.file']

    def _should_import(self):
        """ Before the export, try to read data file from Drupal
        if not found means there where a problem somewhere and we need
        to upload file again.
        """
        assert self.binding_record

        if self.drupal_id:
            record = self.backend_adapter.read(self.drupal_id)

            if not record:
                # in case Drupal id not found force export it
                raise IDMissingInBackend

        return False

    def _has_to_skip(self):
        """
        Return True to skip export record when updating the attachment
        object because Drupal does not support update files
        """
        if self.drupal_id:
            return True
        return False


@drupal
class FileMapper(ExportMapper):
    _model_name = 'drupal.file'
    _path = 'public://'

    @mapping
    def map_file(self, record):
        """ Get current attachment information """
        attachment = record.openerp_id

        return {
            'filename': attachment.name,
            'filepath': self._path+attachment.name,
            'file': attachment.datas,
        }


@drupal
class FileBinder(DrupalModelBinder):
    _model_name = 'drupal.file'



@drupal
class FileAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.file'
    _drupal_model = 'file'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['fid']

    def write(self, id, data):
        _logger.info('Drupal does not support update files, skipping')
        return


@drupal
class FileDeleter(DrupalDeleteSynchronizer):
    _model_name = 'drupal.file'
    _drupal_model = 'file'
