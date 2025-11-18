import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote

import requests
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VismaSignBackend(models.Model):
    _name = "vismasign.backend"
    _description = "Visma Sign Backend"
    _inherit = "connector.backend"
    _rec_name = "company_id"

    base_url = fields.Char(required=True)
    client_identifier = fields.Char(required=True)
    secret_key_b64 = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    binding_ids = fields.One2many("vismasign.binding", "backend_id", readonly=True)

    @api.constrains("base_url")
    def _check_base_url(self):
        for rec in self:
            if rec.base_url.endswith("/"):
                raise ValidationError(_("Base URL must not end with '/'."))

    def _get_secret_key(self):
        return base64.b64decode(self.secret_key_b64 or "")

    def _build_headers(self, method, path, body, content_type=""):
        secret_key = self._get_secret_key()
        md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
        date = format_datetime(datetime.now(timezone.utc))
        string = "\n".join([method, md5, content_type, date, path])
        signature = base64.b64encode(
            hmac.new(secret_key, string.encode(), hashlib.sha512).digest()
        ).decode()
        auth = f"Onnistuu {self.client_identifier}:{signature}"
        return {
            "Content-MD5": md5,
            "Content-Type": content_type,
            "Date": date,
            "Authorization": auth,
        }

    def _request(self, method, path, body=b"", content_type=""):
        url = f"{self.base_url}{path}"
        headers = self._build_headers(method, path, body, content_type)
        try:
            resp = requests.request(method, url, headers=headers, data=body, timeout=30)
        except requests.RequestException as e:
            raise UserError(str(e))
        return resp

    def action_test_connection(self):
        self.ensure_one()
        _logger.info("Testing Visma Sign connection with backend %s", self.id)

        path = "/api/v1/document/00000000-0000-0000-0000-000000000000"

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "GET",
                "endpoint": path,
            }
        )

        try:
            resp = self._request("GET", path)
            successful = resp.status_code in (200, 404)
            binding.write(
                {
                    "status_code": resp.status_code,
                    "response": resp.text,
                    "successful": successful,
                }
            )
        except Exception as e:
            binding.write(
                {
                    "response": str(e),
                    "successful": False,
                }
            )
            raise UserError(_("Connection failed:\n%s") % e)

        if successful:
            raise UserError(
                _("Connection successful. Visma Sign responded with status %s.")
                % resp.status_code
            )

        raise UserError(
            _("Unexpected status code from Visma Sign: %s") % resp.status_code
        )

    def create_document(self, payload):
        self.ensure_one()
        path = "/api/v1/document/"
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = self._build_headers("POST", path, body, "application/json")

        request_data = {
            "url": url,
            "method": "POST",
            "headers": headers,
            "body": body.decode("utf-8"),
        }

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "POST",
                "endpoint": path,
                "payload": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        )

        response = self._request("POST", path, body, "application/json")

        _logger.info("Visma Sign responded with status %s", response.status_code)
        binding.write(
            {
                "status_code": response.status_code,
                "response": response.text,
                "successful": response.status_code == 201,
            }
        )
        if response.status_code != 201:
            _logger.error("Visma Sign document request failed: %s", response.text)
            raise UserError(
                _("Failed to create document in Visma Sign:\n%s") % response.text
            )

        location = response.headers.get("Location")
        _logger.info("Visma Sign Location header: %s", location)

        _logger.info("Visma Sign document request stored in binding %s", binding.id)

        document_uuid = location.rstrip("/").split("/")[-1]
        _logger.info("Visma Sign document created: %s", document_uuid)
        return document_uuid

    def add_file(self, document_uuid, filename, pdf_data):
        self.ensure_one()

        filename_q = quote(filename, safe="")
        path = f"/api/v1/document/{document_uuid}/files?filename={filename_q}"

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "POST",
                "endpoint": path,
            }
        )
        response = self._request("POST", path, pdf_data, "application/pdf")

        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        _logger.info("Visma Sign response_data %s", response_data)

        binding_vals = {
            "status_code": response.status_code,
            "response": response.text,
            "successful": response.status_code == 201,
        }
        binding.write(binding_vals)

        if response.status_code != 201:
            raise UserError(
                _("Visma Sign add file failed: %s\n%s")
                % (response.status_code, response.text)
            )

        file_uuid = response_data.get("uuid")
        if not file_uuid:
            raise UserError(_("Visma Sign did not return file uuid."))

        _logger.info(
            "Visma Sign file added to document %s, file uuid %s",
            document_uuid,
            file_uuid,
        )
        return file_uuid

    def send_invitation(self, document_uuid, recipient_email):
        self.ensure_one()
        path = f"/api/v1/document/{document_uuid}/invitations"

        invite = {"email": recipient_email, "messages": {"send_invitation_email": True}}

        body = json.dumps([invite]).encode("utf-8")

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "POST",
                "endpoint": path,
                "payload": json.dumps([invite], ensure_ascii=False, indent=2),
            }
        )

        response = self._request("POST", path, body, "application/json")

        try:
            response_data = response.json()
        except ValueError:
            response_data = {}

        binding.write(
            {
                "status_code": response.status_code,
                "response": response.text,
                "successful": response.status_code == 201,
            }
        )

        if response.status_code != 201:
            raise UserError(
                _("Visma Sign send invitation failed: %s\n%s")
                % (response.status_code, response.text)
            )

        return response_data

    def get_invitation_status(self, invitation_uuid):
        """
        GET /api/v1/invitation/{invitation_uuid}

        Palauttaa kutsun (invitation) statuksen ja perusdatan Visma Signista.
        """
        self.ensure_one()
        path = f"/api/v1/invitation/{invitation_uuid}"

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "GET",
                "endpoint": path,
            }
        )

        response = self._request("GET", path)

        try:
            data = response.json()
            response_text = json.dumps(data, ensure_ascii=False, indent=2)
        except ValueError:
            data = {}
            response_text = response.text

        binding.write(
            {
                "status_code": response.status_code,
                "response": response_text,
                "successful": response.status_code == 200,
            }
        )

        if response.status_code != 200:
            raise UserError(
                _("Visma Sign get invitation status failed: %s\n%s")
                % (response.status_code, response.text)
            )

        _logger.info(
            "Visma Sign invitation %s status response: %s",
            invitation_uuid,
            data,
        )
        return data
