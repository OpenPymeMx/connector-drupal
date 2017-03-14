# -*- coding: utf-8 -*-

from openerp import SUPERUSER_ID
from openerp.osv import orm, fields
from openerp.tools.translate import _

from openerp.addons.connector.exception import InvalidDataError
from openerp.addons.connector.unit.mapper import (
    ExportMapper, mapping
)
from openerp.addons.connector_drupal_ecommerce.backend import drupal
from openerp.addons.connector_drupal_ecommerce.unit.backend_adapter import (
    DrupalCRUDAdapter, URLNotFound
)
from openerp.addons.connector_drupal_ecommerce.unit.delete_synchronizer import (
    DrupalDeleteSynchronizer
)
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    DrupalExporter
)


class product_product(orm.Model):
    _inherit = 'product.product'

    _columns = {
        'drupal_node_bind_ids': fields.one2many(
            'drupal.product.node', 'openerp_id',
            string="Drupal Node Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_node_bind_ids'] = False
        default['default_code'] = False
        return super(product_product, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_product_node(orm.Model):
    _name = 'drupal.product.node'
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
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A product with same ID on Drupal already exists.'),
    ]


@drupal
class ProductNodeExport(DrupalExporter):
    _model_name = ['drupal.product.node']

    def _export_dependency(
        self, relation, binding_model, exporter_class=None,
        binding_field='drupal_bind_ids', binding_extra_vals=None
    ):
        """
        Export a dependency. The exporter class is a subclass of
        ``DrupalExporter``. If a more precise class need to be defined,
        it can be passed to the ``exporter_class`` keyword argument.
        .. warning:: a commit is done at the end of the export of each
                     dependency. The reason for that is that we pushed a record
                     on the backend and we absolutely have to keep its ID.
                     So you *must* take care not to modify the OpenERP
                     database during an export, excepted when writing
                     back the external ID or eventually to store
                     external data that we have to keep on this side.
                     You should call this method only at the beginning
                     of the exporter synchronization,
                     in :meth:`~._export_dependencies`.
        :param relation: record to export if not already exported
        :type relation: :py:class:`openerp.osv.orm.browse_record`
        :param binding_model: name of the binding model for the relation
        :type binding_model: str | unicode
        :param exporter_cls: :py:class:`openerp.addons.connector\
                                        .connector.ConnectorUnit`
                             class or parent class to use for the export.
                             By default: DrupalExporter
        :type exporter_cls: :py:class:`openerp.addons.connector\
                                       .connector.MetaConnectorUnit`
        :param binding_field: name of the one2many field on a normal
                              record that points to the binding record
                              (default: drupal_bind_ids).
                              It is used only when the relation is not
                              a binding but is a normal record.
        :type binding_field: str | unicode
        :binding_extra_vals:  In case we want to create a new binding
                              pass extra values for this binding
        :type binding_extra_vals: dict
        """
        if not relation:
            return
        if exporter_class is None:
            exporter_class = DrupalExporter

        # wrap is typically True if the relation is for instance a
        # 'product.product' record but the binding model is
        # 'drupal.product.product'
        wrap = relation._model._name != binding_model

        if wrap and hasattr(relation, binding_field):
            domain = [('openerp_id', '=', relation.id),
                      ('backend_id', '=', self.backend_record.id)]
            binding_ids = self.session.search(binding_model, domain)
            if binding_ids:
                assert len(binding_ids) == 1, (
                    'only 1 binding for a backend is '
                    'supported in _export_dependency')
                binding_id = binding_ids[0]
            # we are working with a unwrapped record (e.g.
            # product.category) and the binding does not exist yet.
            # Example: I created a product.product and its binding
            # drupal.product.product and we are exporting it, but we need to
            # create the binding for the product.category on which it
            # depends.
            else:
                ctx = {'connector_no_export': True}
                with self.session.change_context(ctx):
                    with self.session.change_user(SUPERUSER_ID):
                        bind_values = {
                            'backend_id': self.backend_record.id,
                            'openerp_id': relation.id
                        }
                        if binding_extra_vals:
                            bind_values.update(binding_extra_vals)
                        # If 2 jobs create it at the same time, retry
                        # one later. A unique constraint (backend_id,
                        # openerp_id) should exist on the binding model
                        with self._retry_unique_violation():
                            binding_id = self.session.create(
                                binding_model, bind_values
                            )
                            # Eager commit to avoid having 2 jobs
                            # exporting at the same time. The constraint
                            # will pop if an other job already created
                            # the same binding. It will be caught and
                            # raise a RetryableJobError.
                            context = self.session.context
                            if not context.get('__test_no_commit'):
                                self.session.commit()
        else:
            # If drupal_bind_ids does not exist we are typically in a
            # "direct" binding (the binding record is the same record).
            # If wrap is True, relation is already a binding record.
            binding_id = relation.id

        # Instead of supper behavior here we run export for every dependency
        # and relay on _has_to_skip function to avoid send inecesary calls
        exporter = self.get_connector_unit_for_model(
            exporter_class, binding_model
        )
        exporter.run(binding_id)

    def _export_dependencies(self):
        """ Export dependencies for the record """
        self._export_dependency(
            self.binding_record.openerp_id.categ_id,
            'drupal.product.category', exporter_class=ProductCategoryExport,
        )

    def _validate_create_data(self, data):
        """ Check that is set Code on OpenERP product as we are exporting
        to SKU field on Drupal that is master data for commerce
        Raise `InvalidDataError`
        """
        data_product = data['field_product']['und']['form']
        if not data_product['sku']:
            raise InvalidDataError(
                _('The product does not have Code but is mandatory for Drupal')
            )
        return

    def _after_export(self):
        """ After export we need to create the drupal.product.product
        object for being able to export stock levels
        TODO: Refactor as a dependency and stop using commerce_kickstart
              so we could create drupal product first and send as a
              related field to product_display nodes instead of being
              forced to always send product & display nodes at same time
        """
        if len(self.binding_record.drupal_bind_ids) < 1:
            # The drupal.product.product only needs to be created first time
            # product is exported to Drupal
            record = self.backend_adapter.read(self.drupal_id)
            d_product_obj = self.session.pool.get('drupal.product.product')
            d_product_obj.create(
                self.session.cr, self.session.uid,
                {'openerp_id': self.binding_record.openerp_id.id,
                 'drupal_id': record['field_product']['und'][0]['product_id'],
                 'backend_id': self.binding_record.backend_id.id},
                context=self.session.context
            )
        return


@drupal
class ProductNodeMapper(ExportMapper):
    _model_name = 'drupal.product.node'

    direct = [
        ('name', 'title'),
    ]

    @mapping
    def commerce_field_product(self, record):
        """ Get price for current product """
        # TODO: Refactor and find a better way to handle Drupal fields
        product = record.openerp_id

        field_product = {}
        field_product['und'] = {}
        field_product['und']['form'] = {
            'commerce_price': {
                'und': [{
                    'amount': product.list_price,
                    'currency_code': product.company_id.currency_id.name,
                }]
            },
            'title_field': product.name,
            'sku': product.code,
            # commerce_stock is a required field, we send a value for now
            # and updated later after export.
            'commerce_stock': {'und': [{'value': 0}]},
        }

        categories = []
        for taxonomy in product.categ_id.drupal_bind_ids:
            categories.append({'tid': taxonomy.drupal_id})

        return {
            'type': 'product_display',
            'title_field': {'und': [{'value': product.name}]},
            'body': {'und': [{'value': product.description}]},
            'field_product': field_product,
            'field_product_category': {'und': categories[0]}
        }


@drupal
class ProductNodeAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.node'
    _drupal_model = 'node'

    def create(self, data):
        """ Create a record on the external system """
        result = self._call(self._drupal_model, data, 'post')
        return result['nid']

    def delete(self, id):
        """ Delete record from external system"""
        try:
            return super(ProductNodeAdapter, self).delete(id)
        except URLNotFound:
            # Product already have been deleted. Continue without error
            return


@drupal
class ProductNodeDeleter(DrupalDeleteSynchronizer):
    _model_name = 'drupal.product.node'
    _drupal_model = 'node'


class product_category(orm.Model):
    _inherit = 'product.category'

    _columns = {
        'drupal_bind_ids': fields.one2many(
            'drupal.product.category', 'openerp_id',
            string="Drupal Bindings"
        ),
    }

    def copy_data(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default['drupal_bind_ids'] = False
        return super(product_category, self).copy_data(
            cr, uid, id, default=default, context=context
        )


class drupal_product_category(orm.Model):
    _name = 'drupal.product.category'
    _inherit = 'drupal.binding'
    _inherits = {'product.category': 'openerp_id'}
    _description = 'Drupal Product Category'

    _rec_name = 'name'

    _columns = {
        'openerp_id': fields.many2one(
            'product.category', string='Product Category',
            required=True, ondelete='cascade'
        ),
        'created_at': fields.datetime(
            'Created At (on Drupal)', readonly=True
        ),
        'updated_at': fields.datetime(
            'Updated At (on Drupal)', readonly=True
        ),
        'vid': fields.related(
            'backend_id', 'drupal_vocabulary_id', 'drupal_id',
            type='integer', relation='drupal.vocabulary',
            string='Drupal Vocabulary', store=True
        )
    }

    _sql_constraints = [
        ('drupal_uniq', 'unique(backend_id, drupal_id)',
         'A taxonomy with same ID on Drupal already exists.'),
    ]

    def _check_main_category(self, cr, uid, ids, context=None):
        """
        Check the binded record is not the same mapped with Drupal Vocabulary
        """
        context = context or {}
        record = self.browse(cr, uid, ids, context=context)[0]
        backend = record.backend_id
        if record.openerp_id.id == backend.main_product_category_id.id:
            return True
        return False

    _constraint = [
        (_check_main_category,
         _('You cannot export category mapped to Drupal Vocabulary'),
         ['vid'])
    ]


@drupal
class ProductCategoryExport(DrupalExporter):
    _model_name = ['drupal.product.category']

    def _export_dependencies(self):
        """ Export the parent category for the record"""
        backend = self.backend_record
        category = self.binding_record.openerp_id

        # Parent category is mapped to Drupal vocabulary, do not export it
        is_main = category.parent_id.id == backend.main_product_category_id.id
        if is_main:
            return

        self._export_dependency(
            self.binding_record.openerp_id.parent_id,
            'drupal.product.category', exporter_class=ProductCategoryExport,
        )


@drupal
class ProductCategoryExportMapper(ExportMapper):
    _model_name = 'drupal.product.category'

    direct = [
        ('name', 'name'),
        ('vid', 'vid'),
    ]

    @mapping
    def parent_category(self, record):
        """
        Get parent category in order to export the hierarchy categories
        created on OpenERP to Drupal
        """
        parent_id = None
        category = record.openerp_id
        backend = record.backend_id

        # Does the parent category is the category mapped to Vocabulary?
        is_main = category.parent_id.id == backend.main_product_category_id.id

        if category.parent_id and not is_main:
            parent_id = category.parent_id.drupal_bind_ids[0].drupal_id

        return {'parent': parent_id}


@drupal
class ProductCategoryAdapter(DrupalCRUDAdapter):
    _model_name = 'drupal.product.category'
    _drupal_model = 'taxonomy_term'

    def create(self, data):
        """ Override method to extract id for new record"""
        result = super(ProductCategoryAdapter, self).create(data)
        # for some reason result is a list. so we retrieve the first item.
        return result['tid']

    def write(self, id, data):
        """ Override method to add id for record into data """
        data['tid'] = id
        return DrupalCRUDAdapter.write(self, id, data)


@drupal
class ProductCategoryDeleter(DrupalDeleteSynchronizer):
    _model_name = 'drupal.product.category'
    _drupal_model = 'taxonomy_term'
