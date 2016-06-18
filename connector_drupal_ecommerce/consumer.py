# -*- coding: utf-8 -*-

from openerp.addons.connector.connector import Binder
from openerp.addons.connector.event import (
    on_record_write, on_record_create, on_record_unlink
)

from .connector import get_environment
from .unit.export_synchronizer import export_record
from .unit.delete_synchronizer import export_delete_record

_MODEL_NAMES = ()
_BIND_MODEL_NAMES = ()


@on_record_create(model_names=_BIND_MODEL_NAMES)
@on_record_write(model_names=_BIND_MODEL_NAMES)
def delay_export(session, model_name, record_id, vals):
    """ Delay a job which export a binding record.

    (A binding record being a ``drupal.res.partner``,
    ``drupal.product.product``, ...)
    """
    if session.context.get('connector_no_export'):
        return
    fields = vals.keys()
    export_record.delay(session, model_name, record_id, fields=fields)


@on_record_write(model_names=_MODEL_NAMES)
def delay_export_all_bindings(session, model_name, record_id, vals):
    """ Delay a job which export all the bindings of a record.

    In this case, it is called on records of normal models and will delay
    the export for all the bindings.
    """
    if session.context.get('connector_no_export'):
        return
    model = session.pool.get(model_name)
    record = model.browse(
        session.cr, session.uid, record_id, context=session.context
    )
    fields = vals.keys()
    for binding in record.drupal_bind_ids:
        export_record.delay(
            session, binding._model._name, binding.id, fields=fields
        )


@on_record_unlink(model_names=_BIND_MODEL_NAMES)
def delay_unlink(session, model_name, record_id):
    """
    Delay a job which delete a record on Drupal.
    Called on binding records."""
    model = session.pool.get(model_name)
    record = model.browse(
        session.cr, session.uid, record_id, context=session.context
    )
    env = get_environment(session, model_name, record.backend_id.id)
    binder = env.get_connector_unit(Binder)
    drupal_id = binder.to_backend(record_id)
    if drupal_id:
        export_delete_record.delay(
            session, model_name, record.backend_id.id, drupal_id
        )
