import base64
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Agreement(models.Model):
    _inherit = "agreement"

    vismasign_document_uuid = fields.Char(readonly=True, copy=False)
    vismasign_file_uuid = fields.Char(readonly=True, copy=False)
    vismasign_invitation_uuid = fields.Char(readonly=True, copy=False)
    vismasign_status = fields.Char(readonly=True, copy=False, tracking=True)
    vismasign_last_check = fields.Datetime(readonly=True, copy=False)
    vismasign_signed_attachment_id = fields.Many2one(
        "ir.attachment", readonly=True, copy=False
    )

    def action_vismasign_send(self):
        """
        Send the agreement PDF to Visma Sign for electronic signing.

        Workflow:
        1. Read the configured report XML-ID from system settings.
        2. Render the agreement PDF with the configured report.
        3. Create a document in Visma Sign.
        4. Upload the PDF file to the created document.
        5. Send a signing invitation to the customer email.
        6. Store returned UUIDs and the current signing status on the agreement.

        Raises:
            UserError: If the agreement is a template, no backend is configured,
                       no customer email exists, or the configured report cannot
                       be rendered.
        """
        self.ensure_one()

        if self.is_template:
            raise UserError(_("A template agreement cannot be sent for signature."))

        if not self.partner_id.email:
            raise UserError(_("The customer does not have an email address."))

        backend = self.env["vismasign.backend"].search(
            [("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if not backend:
            raise UserError(
                _("No Visma Sign backend is configured for company %s.")
                % self.company_id.display_name
            )

        # sudo: reading a system parameter requires group_system, which the
        # calling user (e.g. a salesperson) does not necessarily have
        report_xmlid = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("agreement_vismasign.report_xmlid")
        )
        if not report_xmlid:
            raise UserError(
                _(
                    "No Visma Sign report is configured. Set the report XML-ID "
                    "under Settings > Agreements > Visma Sign."
                )
            )

        try:
            # sudo: rendering the report is a technical action; the calling
            # user only needs read access to the agreement, not to the report
            # action itself
            pdf = (
                self.env["ir.actions.report"]
                .sudo()
                ._render_qweb_pdf(
                    report_xmlid,
                    [self.id],
                )[0]
            )
        except Exception as exc:
            _logger.exception(
                "Failed to render report %s for agreement %s",
                report_xmlid,
                self.id,
            )
            raise UserError(
                _("Failed to render the configured agreement report: %s") % report_xmlid
            ) from exc

        payload = {
            "document": {
                "name": self.display_name,
            }
        }

        document_uuid = backend.create_document(payload)
        file_uuid = backend.add_file(document_uuid, f"{self.code}.pdf", pdf)
        invitation_data = backend.send_invitation(document_uuid, self.partner_id.email)

        invitation_uuid = False
        invitation_status = False

        if isinstance(invitation_data, list) and invitation_data:
            invitation_uuid = invitation_data[0].get("uuid")
            invitation_status = invitation_data[0].get("status")
        elif isinstance(invitation_data, dict):
            invitation_uuid = invitation_data.get("uuid")
            invitation_status = invitation_data.get("status")

        self.write(
            {
                "vismasign_document_uuid": document_uuid,
                "vismasign_file_uuid": file_uuid,
                "vismasign_invitation_uuid": invitation_uuid,
                "vismasign_status": invitation_status,
                "vismasign_last_check": fields.Datetime.now(),
            }
        )

        self.message_post(
            body=_("The agreement was sent to Visma Sign for electronic signing."),
            subtype_xmlid="mail.mt_note",
        )

    @api.model
    def cron_update_vismasign_status(self):
        """
        Scheduled task that synchronizes Visma Sign invitation statuses to agreements.

        Workflow:
        - Find agreements that have an invitation UUID and are either not yet
          marked as signed, or signed but still missing their signed
          attachment (e.g. a previous attempt to download it failed).
        - Fetch the latest invitation status from Visma Sign.
        - Update the local status and timestamp.
        - When the status becomes 'signed':
            * download the signed PDF (once, kept on
              ``vismasign_signed_attachment_id``)
            * post a chatter message
        """
        backends = self.env["vismasign.backend"].search([])

        for backend in backends:
            agreements = self.search(
                [
                    ("vismasign_invitation_uuid", "!=", False),
                    ("company_id", "=", backend.company_id.id),
                    "|",
                    ("vismasign_status", "!=", "signed"),
                    ("vismasign_signed_attachment_id", "=", False),
                ]
            )

            for agreement in agreements:
                try:
                    data = backend.get_invitation_status(
                        agreement.vismasign_invitation_uuid
                    )
                except UserError as exc:
                    _logger.warning(
                        "Failed to fetch Visma Sign invitation status for agreement %s: %s",  # noqa: E501
                        agreement.id,
                        exc,
                    )
                    continue

                status = data.get("status")

                agreement.write(
                    {
                        "vismasign_status": status,
                        "vismasign_last_check": fields.Datetime.now(),
                    }
                )

                if status != "signed" or not agreement.vismasign_document_uuid:
                    continue

                try:
                    self._process_vismasign_signed(agreement, backend)
                except Exception:
                    # One malformed record must not roll back the status
                    # updates already applied to the other agreements in
                    # this cron run.
                    _logger.exception(
                        "Failed to process the signed Visma Sign document for "
                        "agreement %s",
                        agreement.id,
                    )

    def _process_vismasign_signed(self, agreement, backend):
        """Attach the signed PDF (once) and notify followers."""
        if not agreement.vismasign_signed_attachment_id:
            try:
                signed_pdf = backend.get_document_file(
                    agreement.vismasign_document_uuid,
                    index=0,
                )
            except UserError as exc:
                _logger.warning(
                    "Failed to download signed Visma Sign document for agreement %s: %s",  # noqa: E501
                    agreement.id,
                    exc,
                )
                return

            if not signed_pdf:
                _logger.warning(
                    "Empty signed document content for agreement %s",
                    agreement.id,
                )
                return

            attachment = self.env["ir.attachment"].create(
                {
                    "name": _("Agreement - %s (signed).pdf") % agreement.display_name,
                    "res_model": agreement._name,
                    "res_id": agreement.id,
                    "company_id": agreement.company_id.id,
                    "type": "binary",
                    "datas": base64.b64encode(signed_pdf),
                    "mimetype": "application/pdf",
                }
            )
            agreement.vismasign_signed_attachment_id = attachment.id

        message_body = (
            Markup(
                "<p>The agreement <strong>%s</strong> has been signed "
                "in Visma Sign.</p>"
            )
            % agreement.display_name
        )

        agreement.message_post(
            body=message_body,
            subtype_xmlid="mail.mt_comment",
        )
