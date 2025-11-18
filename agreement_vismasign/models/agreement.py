from odoo import _, api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class Agreement(models.Model):
    _inherit = "agreement"

    vismasign_document_uuid = fields.Char(readonly=True)
    vismasign_file_uuid = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        agreements = super().create(vals_list)
        for agreement in agreements:
            agreement.action_vismasign_send()
        return agreements

    def action_vismasign_send(self):
        self.ensure_one()

        backend = self.env["vismasign.backend"].search([], limit=1)
        if not backend:
            raise UserError(
                _(
                    "No Visma Sign backend configured. "
                    "Please configure a Visma Sign backend first."
                )
            )

        # LUO PDF TIEDOSTO ACTIONIN KAUTTA
        pdf = (
            self.env["ir.actions.report"]
            .sudo()
            ._render_qweb_pdf(
                "agreement_vismasign.action_agreement_report_template",
                [self.id],
            )[0]
        )
        _logger.info("Generated PDF %s", pdf)

        payload = {
            "document": {
                "name": self.name,
            }
        }

        # LUODAAN LOCATION VISMA SIGN -DOKUMENTILLE
        document_uuid = backend.create_document(payload)

        file_uuid = backend.add_file(document_uuid, self.name, pdf)

        self.write({
            "vismasign_document_uuid": document_uuid,
            "vismasign_file_uuid": file_uuid,
        })

        invitation = backend.send_invitation(document_uuid, self.partner_id.email)

        _logger.info(
            "Agreement %s sent to Visma Sign, document %s, file %s",
            self.id,
            document_uuid,
            file_uuid,
        )
