from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    agreement_vismasign_report_xmlid = fields.Char(
        string="Visma Sign Report XML-ID",
        config_parameter="agreement_vismasign.report_xmlid",
    )
