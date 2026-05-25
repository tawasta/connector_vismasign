import base64
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    state = fields.Selection(selection_add=[("signed", "Signed Agreement")])

    vismasign_document_uuid = fields.Char(readonly=True, copy=False)
    vismasign_file_uuid = fields.Char(readonly=True, copy=False)
    vismasign_invitation_uuid = fields.Char(readonly=True, copy=False)
    vismasign_status = fields.Char(readonly=True, copy=False, tracking=True)
    vismasign_last_check = fields.Datetime(readonly=True, copy=False)

    def action_vismasign_send(self):
        """
        Send the quotation PDF to Visma Sign for electronic signing.

        Workflow:
        1. Read the configured report XML-ID from system settings.
        2. Render the quotation PDF with the configured report.
        3. Create a document in Visma Sign.
        4. Upload the PDF file to the created document.
        5. Send a signing invitation to the customer email.
        6. Store returned UUIDs and the current signing status on the sale order.

        Raises:
            UserError: If no backend is configured, no customer email exists,
                       or the configured report cannot be rendered.
        """
        self.ensure_one()

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

        report_xmlid = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sale_vismasign.report_xmlid",
                default="sale.action_report_saleorder",
            )
        )

        try:
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
                "Failed to render report %s for sale order %s",
                report_xmlid,
                self.id,
            )
            raise UserError(
                _("Failed to render the configured quotation report: %s") % report_xmlid
            ) from exc

        payload = {
            "document": {
                "name": self.name,
            }
        }

        document_uuid = backend.create_document(payload)
        file_uuid = backend.add_file(document_uuid, f"{self.name}.pdf", pdf)
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
            body=_("The quotation was sent to Visma Sign for electronic signing."),
            subtype_xmlid="mail.mt_note",
        )

    @api.model
    def cron_update_vismasign_status(self):
        """
        Scheduled task that synchronizes Visma Sign invitation statuses to sale orders.

        Workflow:
        - Find sale orders that have an invitation UUID and are not yet marked as signed.
        - Fetch the latest invitation status from Visma Sign.
        - Update the local status and timestamp.
        - When the status becomes 'signed':
            * download the signed PDF
            * store it as an attachment on the sale order
            * post a chatter message
            * either confirm the quotation or move it to the custom 'signed' state,
              depending on the configured system setting

        The post-sign action is controlled by:
            sale_vismasign.post_sign_action
                - confirm
                - signed
        """
        backends = self.env["vismasign.backend"].search([])

        post_sign_action = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sale_vismasign.post_sign_action",
                default="confirm",
            )
        )

        for backend in backends:
            sale_orders = self.search(
                [
                    ("vismasign_invitation_uuid", "!=", False),
                    ("company_id", "=", backend.company_id.id),
                    ("vismasign_status", "!=", "signed"),
                ]
            )

            for sale_order in sale_orders:
                try:
                    data = backend.get_invitation_status(
                        sale_order.vismasign_invitation_uuid
                    )
                except UserError as exc:
                    _logger.warning(
                        "Failed to fetch Visma Sign invitation status for sale order %s: %s",
                        sale_order.id,
                        exc,
                    )
                    continue

                status = data.get("status")

                sale_order.write(
                    {
                        "vismasign_status": status,
                        "vismasign_last_check": fields.Datetime.now(),
                    }
                )

                if status != "signed" or not sale_order.vismasign_document_uuid:
                    continue

                attachment_name = "Sale Order - %s (signed).pdf" % sale_order.name

                existing_attachment = self.env["ir.attachment"].search(
                    [
                        ("res_model", "=", sale_order._name),
                        ("res_id", "=", sale_order.id),
                        ("name", "=", attachment_name),
                    ],
                    limit=1,
                )

                if not existing_attachment:
                    try:
                        signed_pdf = backend.get_document_file(
                            sale_order.vismasign_document_uuid,
                            index=0,
                        )
                    except UserError as exc:
                        _logger.warning(
                            "Failed to download signed Visma Sign document for sale order %s: %s",
                            sale_order.id,
                            exc,
                        )
                        continue

                    if not signed_pdf:
                        _logger.warning(
                            "Empty signed document content for sale order %s",
                            sale_order.id,
                        )
                        continue

                    self.env["ir.attachment"].create(
                        {
                            "name": attachment_name,
                            "res_model": sale_order._name,
                            "res_id": sale_order.id,
                            "type": "binary",
                            "datas": base64.b64encode(signed_pdf),
                            "mimetype": "application/pdf",
                        }
                    )

                salesperson_partner = sale_order.user_id.partner_id

                message_body = (
                    Markup(
                        "<p>The quotation <strong>%s</strong> has been signed in Visma Sign.</p>"
                    )
                    % sale_order.name
                )

                partner_ids = []
                if salesperson_partner:
                    partner_ids.append(salesperson_partner.id)

                sale_order.message_post(
                    body=message_body,
                    subtype_xmlid="mail.mt_comment",
                    partner_ids=partner_ids,
                )

                if post_sign_action == "confirm":
                    if sale_order.state in ("draft", "sent"):
                        try:
                            sale_order.action_confirm()
                        except Exception as exc:
                            _logger.warning(
                                "Failed to confirm sale order %s after signing: %s",
                                sale_order.id,
                                exc,
                            )
                elif post_sign_action == "signed":
                    if sale_order.state in ("draft", "sent"):
                        sale_order.write({"state": "signed"})
