# -*- coding: utf-8 -*-

from openerp.tools.translate import _
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.unit.synchronizer import DeleteSynchronizer
from ..connector import get_environment


class DrupalDeleteSynchronizer(DeleteSynchronizer):
    """ Base deleter for Drupal """

    def run(self, drupal_id):
        """ Run the synchronization, delete the record on Drupal
        :param drupal_id: identifier of the record to delete
        """
        self.backend_adapter.delete(drupal_id)
        return _('Record %s deleted on Drupal') % drupal_id


@job
def export_delete_record(session, model_name, backend_id, drupal_id):
    """ Delete a record on Drupal """
    env = get_environment(session, model_name, backend_id)
    deleter = env.get_connector_unit(DrupalDeleteSynchronizer)
    return deleter.run(drupal_id)
