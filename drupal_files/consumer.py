# -*- coding: utf-8 -*-

from openerp.addons.connector.event import on_record_unlink

import openerp.addons.connector_drupal_ecommerce.consumer as drupalconnect


@on_record_unlink(model_names=['drupal.file'])
def delay_unlink(session, model_name, record_id):
    drupalconnect.delay_unlink(session, model_name, record_id)
