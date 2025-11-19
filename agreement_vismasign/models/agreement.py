from odoo import _, api, fields, models
from odoo.exceptions import UserError
import logging
import base64

_logger = logging.getLogger(__name__)


class Agreement(models.Model):
    _inherit = "agreement"

    vismasign_document_uuid = fields.Char(readonly=True)
    vismasign_file_uuid = fields.Char(readonly=True)
    vismasign_invitation_uuid = fields.Char(readonly=True)
    vismasign_status = fields.Char(readonly=True)
    vismasign_last_check = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        agreements = super().create(vals_list)
        for agreement in agreements:
            agreement.action_vismasign_send()
        return agreements

    def action_vismasign_send(self):
        """
        Send the agreement to Visma Sign for electronic signing.

        Steps:
        1. Generate a PDF using the agreement report template.
        2. Create a document in Visma Sign.
        3. Upload the PDF file to Visma Sign.
        4. Send a signing invitation to the partner's email address.
        5. Store all UUIDs and initial status on the Agreement record.

        Raises:
            UserError: If no backend is configured or API calls fail.
        """
        self.ensure_one()

        backend = self.env["vismasign.backend"].search([], limit=1)
        if not backend:
            raise UserError(
                _(
                    "No Visma Sign backend configured. "
                    "Please configure a Visma Sign backend first."
                )
            )

        pdf = (
            self.env["ir.actions.report"]
            .sudo()
            ._render_qweb_pdf(
                "agreement_vismasign.action_agreement_report_template",
                [self.id],
            )[0]
        )

        payload = {
            "document": {
                "name": self.name,
            }
        }

        document_uuid = backend.create_document(payload)

        file_uuid = backend.add_file(document_uuid, self.name, pdf)
        invitation_data = backend.send_invitation(document_uuid, self.partner_id.email)
        inv_uuid = False
        inv_status = False

        if isinstance(invitation_data, list) and invitation_data:
            inv_uuid = invitation_data[0].get("uuid")
            inv_status = invitation_data[0].get("status")
        elif isinstance(invitation_data, dict):
            inv_uuid = invitation_data.get("uuid")
            inv_status = invitation_data.get("status")

        self.write(
            {
                "vismasign_document_uuid": document_uuid,
                "vismasign_file_uuid": file_uuid,
                "vismasign_invitation_uuid": inv_uuid,
                "vismasign_status": inv_status,
                "vismasign_last_check": fields.Datetime.now(),
            }
        )

    @api.model
    def cron_update_vismasign_status(self):
        """
        Scheduled task that updates the signing status of agreements in Visma Sign.

        This method is executed via ir.cron every 15 minutes.

        Workflow:
        - Find agreements with an active invitation UUID and status other than "signed".
        - Fetch the current status from Visma Sign.
        - Update the status on the Agreement record.
        - If the status transitions to "signed":
            * Download the signed PDF using the backend
            * Save it as an attachment on the Agreement
            * Ensure duplicates are not created

        This ensures that the fully signed document is automatically stored
        in Odoo once the signing is completed in Visma Sign.
        """
        backends = self.env["vismasign.backend"].search([])
        for backend in backends:
            agreements = self.search(
                [
                    ("vismasign_invitation_uuid", "!=", False),
                    ("company_id", "=", backend.company_id.id),
                    ("vismasign_status", "!=", "signed"),
                ]
            )

            for agreement in agreements:
                try:
                    data = backend.get_invitation_status(
                        agreement.vismasign_invitation_uuid
                    )
                except UserError as e:
                    _logger.warning(
                        "Failed to fetch Visma Sign invitation status for agreement %s: %s",
                        agreement.id,
                        e,
                    )
                    continue

                status = data.get("status")

                agreement.write(
                    {
                        "vismasign_status": status,
                        "vismasign_last_check": fields.Datetime.now(),
                    }
                )

                if status == "signed" and agreement.vismasign_document_uuid:
                    attachment_name = "Agreement - %s (signed).pdf" % (agreement.name,)

                    try:
                        signed_pdf = backend.get_document_file(
                            agreement.vismasign_document_uuid, index=0
                        )
                    except UserError as e:
                        _logger.warning(
                            "Failed to download signed Visma Sign document for agreement %s: %s",
                            agreement.id,
                            e,
                        )
                        continue

                    if not signed_pdf:
                        _logger.warning(
                            "Empty signed document content for agreement %s",
                            agreement.id,
                        )
                        continue

                    self.env["ir.attachment"].create(
                        {
                            "name": attachment_name,
                            "res_model": agreement._name,
                            "res_id": agreement.id,
                            "type": "binary",
                            "datas": base64.b64encode(signed_pdf),
                            "mimetype": "application/pdf",
                        }
                    )
