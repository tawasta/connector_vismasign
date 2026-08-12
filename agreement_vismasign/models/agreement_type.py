from odoo import fields, models


class AgreementType(models.Model):
    _inherit = "agreement.type"

    report_xmlid = fields.Char(
        string="Visma Sign Report XML-ID",
        help="Technical XML-ID of the report action used to render the "
        "document sent to Visma Sign for agreements of this type, e.g. "
        "sale.action_report_saleorder.",
    )
