from odoo import _, api, fields, models
from odoo.exceptions import UserError
import logging

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

        _logger.info(
            "Agreement %s sent to Visma Sign, document %s, file %s",
            self.id,
            document_uuid,
            file_uuid,
        )

    @api.model
    def cron_update_vismasign_status(self):
        """
        Päivittää Visma Sign -kutsujen statukset invitation_uuid:n perusteella.
        Ajetaan ir.cronilla.

        Jos status päivittyy Signed-tilaan, haetaan allekirjoitettu
        dokumentti Visma Signista ja tallennetaan se Agreementin liitteisiin.
        """
        backends = self.env["vismasign.backend"].search([])
        for backend in backends:
            agreements = self.search(
                [
                    ("vismasign_invitation_uuid", "!=", False),
                    ("company_id", "=", backend.company_id.id),
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
                prev_status = agreement.vismasign_status

                agreement.write(
                    {
                        "vismasign_status": status,
                        "vismasign_last_check": fields.Datetime.now(),
                    }
                )

                _logger.info(
                    "Updated Visma Sign status for agreement %s to %s",
                    agreement.id,
                    status,
                )

                # Jos status on Signed ja meillä on document_uuid,
                # haetaan allekirjoitettu PDF ja tallennetaan liitteeksi.
                if (
                    status == "Signed"
                    and agreement.vismasign_document_uuid
                ):
                    # Tarkistetaan, onko allekirjoitettu liite jo olemassa,
                    # ettei luoda duplikaatteja jokaisella cron-ajolla.
                    attachment_name = "Agreement - %s (signed).pdf" % (agreement.name,)
                    existing_attachment = self.env["ir.attachment"].search(
                        [
                            ("res_model", "=", agreement._name),
                            ("res_id", "=", agreement.id),
                            ("name", "=", attachment_name),
                        ],
                        limit=1,
                    )

                    if existing_attachment:
                        _logger.info(
                            "Signed attachment already exists for agreement %s, skipping download",
                            agreement.id,
                        )
                        continue

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

                    _logger.info(
                        "Created signed PDF attachment for agreement %s",
                        agreement.id,
                    )
