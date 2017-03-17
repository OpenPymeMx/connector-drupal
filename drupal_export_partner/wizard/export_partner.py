# -*- coding: utf-8 -*-

from openerp.osv import orm, fields


class export_partner(orm.TransientModel):
    """
    Wizard for select backend to where export a product
    """
    _name = 'drupal.export.partner'

    _columns = {
        'backend_id': fields.many2one(
            'drupal.backend', string='Drupal Backend', required=True
        )
    }

    def export_to_drupal(self, cr, uid, ids, context=None):
        """
        Export selected partner to Drupal

        It groups the products by backend to discover if partner
        already have been exported or is export by first time.

        If partner is exported by first time this wizard creates the
        corresponding drupal.res.partner object and let the consumer
        manages the new export job creation and execution.
        """
        context = context or {}
        bind_obj = self.pool.get('drupal.res.partner')
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
