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

import openerp.addons.connector_drupal_ecommerce.consumer as drupalconnect
from openerp.addons.connector.event import (
    on_record_create, on_record_unlink
)
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    export_record
)


@on_record_create(model_names='drupal.product.pricelist')
def export_pricelist(session, model_name, record_id, vals):
    """ Delay a job which export a binding record.

    (A binding record being a ``drupal.res.partner``,
    ``drupal.product.product``, ...)
    """
    if session.context.get('connector_no_export'):
        return
    fields = vals.keys()
    export_record.delay(session, model_name, record_id, fields=fields)


@on_record_unlink(model_names=['drupal.product.pricelist'])
def delay_unlink(session, model_name, record_id):
    """Unlink all price items related with deleted pricelist
    """
    priceitems_ids = session.pool.get('drupal.product.priceitem').search(
        session.cr, session.uid,
        [('pricelist_id', '=', record_id)],
        context=session.context,
    )
    for item_id in priceitems_ids:
        drupalconnect.delay_unlink(
            session, 'drupal.product.priceitem', item_id,
        )
