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

from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import export_record


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
        """
        context = context or {}
        pricelist_obj = self.pool.get('product.pricelist')

        session = ConnectorSession(cr, uid, context=context)
        record_ids = context['active_ids']
        backend = self.browse(cr, uid, ids, context=context)[0].backend_id

        for record in pricelist_obj.browse(
            cr, uid, record_ids, context=context
        ):
            # If there is no binding object created yet then we create
            if not len(record.drupal_bind_ids):
                vals = {
                    'openerp_id': record.id,
                    'backend_id': backend.id
                }
                pricelist_obj.write(
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
