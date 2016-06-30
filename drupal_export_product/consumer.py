# -*- coding: utf-8 -*-

import openerp.addons.connector_drupal_ecommerce.consumer as drupalconnect

from openerp.addons.connector.event import (
    on_record_create, on_record_write, on_record_unlink
)
from openerp.addons.connector_drupal_ecommerce.unit.export_synchronizer import (
    export_record
)


@on_record_write(model_names='product.category')
def delay_export_all_bindings(session, model_name, record_id, vals):
    """ Delay a job which export all the bindings of a record.

    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    fields = ['vid', 'name', 'parent_id']
    # Only export the object if changed one of the mapped fields
    if not any((True for x in vals.keys() if x in fields)):
        return
    drupalconnect.delay_export_all_bindings(
        session, model_name, record_id, dict.fromkeys(fields, 0)
    )


@on_record_create(model_names='drupal.product.node')
def export_product_node(session, model_name, record_id, vals):
    """ Delay a job which export all node bindings record
    (A binding record being a ``drupal.product.node``)
    """
    if session.context.get('connector_no_export'):
        return
    export_record.delay(session, model_name, record_id)


@on_record_write(model_names='product.product')
def delay_export_node_bindings(session, model_name, record_id, vals):
    """ Delay a job which export all the bindings of a record.

    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    drupalconnect.delay_export_all_bindings(
        session, model_name, record_id, vals
    )

@on_record_unlink(model_names=['drupal.product.node',
                               'drupal.product.product',
                               'drupal.product.category'])
def delay_unlink(session, model_name, record_id):
    drupalconnect.delay_unlink(session, model_name, record_id)
