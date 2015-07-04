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

from openerp.addons.connector.event import (
    on_record_write, on_record_unlink
)
from openerp.addons.connector_drupal_ecommerce import consumer


@on_record_write(model_names=['product.product', 'product.category'])
def delay_export_all_bindings(session, model_name, record_id, vals):
    consumer.delay_export_all_bindings(
        session, model_name, record_id, vals
    )
