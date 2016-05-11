# -*- coding: utf-8 -*-

from openerp.osv import fields, orm

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


class ir_attachment(orm.Model):
    _inherit = 'ir.attachment'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.file', 'openerp_id',
            string="Drupal Node Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_file_bind_ids'] = False
        return super(ir_attachment, self).copy_data(
            cr, uid, id, default=default, context=context
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
class FileAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.file'
    _drupal_model = 'file'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['fid']


@drupal
class FileBinder(DrupalModelBinder):
    _model_name = 'drupal.file'
