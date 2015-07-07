# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright 2015 OpenPyme México
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


class export_pricelist(orm.TransientModel):
    """
    Wizard for select backend to where export a product
    """
    _name = 'drupal.export.pricelist'

    _columns = {
        'backend_id': fields.many2one(
            'drupal.backend', string='Drupal Backend', required=True
        )
    }

    def export_to_drupal(self, cr, uid, ids, context=None):
        """
        Export selected pricelist to Drupal
        TODO: Refactor for use a common wizard
              the wizard must be able to prevent multiple export of
              drupal.product.node when creating pricelist
        """
        context = context or {}
        bind_obj = self.pool.get('drupal.product.pricelist')
        existing_ids = []

        record_ids = context['active_ids']
        backend = self.browse(cr, uid, ids, context=context)[0].backend_id

        # Search the `drupal model for the records that already exist
        binding_ids = bind_obj.search(
            cr, uid,
            [('openerp_id', 'in', record_ids),
             ('backend_id', '=', backend.id)],
            context=context
        )

        for binding in bind_obj.browse(cr, uid, binding_ids, context=context):
            existing_ids.append(binding.openerp_id.id)

        # Create missing binding records,
        # the consumer will launch the actual export
        for record_id in record_ids:
            if record_id not in existing_ids:
                bind_obj.create(
                    cr, uid,
                    {'openerp_id': record_id, 'backend_id': backend.id},
                    context=context
                )
        return
