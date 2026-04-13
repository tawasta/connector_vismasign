from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    vismasign_report_xmlid = fields.Char(
        string="Visma Sign Report XML-ID",
        config_parameter="sale_vismasign.report_xmlid",
        default="sale.action_report_saleorder",
    )

    vismasign_post_sign_action = fields.Selection(
        selection=[
            ("confirm", "Confirm quotation"),
            ("signed", "Set quotation as signed"),
        ],
        string="Action After Signing",
        config_parameter="sale_vismasign.post_sign_action",
        default="confirm",
    )