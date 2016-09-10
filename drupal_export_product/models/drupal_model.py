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
from openerp import SUPERUSER_ID

from openerp.addons.connector.session import ConnectorSession

from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    export_record
)
from openerp.addons.connector_drupal_ecommerce.unit.import_synchronizer import (
    import_batch
)


class drupal_backend(orm.Model):
    """
    Extends base drupal backend class for add fields to define the way we are
    going to map product categories with Drupal vocabularies & taxonomy terms
    """
    _inherit = 'drupal.backend'

    _columns = {
        'drupal_vocabulary_id': fields.many2one(
            'drupal.vocabulary', 'Vocabulary'
        ),
        'main_product_category_id': fields.many2one(
            'product.category', 'Main product category'
        )
    }

    def _get_default_category(self, cr, uid, context=None):
        """ Get default product category for current backend """
        categ_ids = self.pool.get('product.category').search(
            cr, uid,
            [('parent_id', '=', False)],
            context=context
        )
        return categ_ids[0] or False

    _defaults = {
        'main_product_category_id': _get_default_category
    }

    def import_vocabulary(self, cr, uid, ids, context=None):
        """
        Get all vocabularies defined on Drupal site to map into the product
        categories used on OpenERP
        """
        context = context or {}
        if not hasattr(ids, '__iter__'):
            ids = [ids]

        session = ConnectorSession(cr, uid, context=context)
        for backend_id in ids:
            import_batch(session, 'drupal.vocabulary', backend_id)

        return True

    def export_product_categories(self, cr, uid, ids, context=None):
        """
        Export product categories to Drupal
        """
        context = context or {}
        session = ConnectorSession(cr, uid, context=context)

        categ_obj = self.pool.get('product.category')
        bind_obj = self.pool.get('drupal.product.category')

        backend = self.browse(cr, uid, ids, context=context)[0]
        vocabulary = backend.main_product_category_id

        record_ids = categ_obj.search(
            cr, uid,
            [('id', 'child_of', [vocabulary.id])]
        )

        # Exclude send the category mapped to Drupal Vocabulary
        record_ids = [x for x in record_ids if x != vocabulary.id]

        # Create missing binding records, and send them to Drupal
        # Usually this is a one time operation so we can afford wait and block
        # the user interface for the time the export is being doing
        for record in categ_obj.browse(cr, uid, record_ids, context=context):
            # Refresh the record cache because maybe we have created the bind
            # object as export dependency resolution.
            record.refresh()
            if not record.drupal_bind_ids:
                bind_id = bind_obj.create(
                    cr, uid,
                    {'openerp_id': record.id, 'backend_id': backend.id},
                    context=context
                )
                export_record(
                    session, 'drupal.product.category', bind_id,
                    fields=['name', 'parent', 'sequence', 'vid']
                )

        return True

    def unlink(self, cr, uid, ids, context=None):
        vocab_obj = self.pool.get('drupal.vocabulary')
        for record in self.browse(cr, uid, ids, context=context):
            vocab_obj.unlink(
                cr, SUPERUSER_ID, [record.drupal_vocabulary_id.id],
                context=context
            )
        return super(drupal_backend, self).unlink(
            cr, uid, ids, context=context
        )
