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
    """
    Backend connector for communicating with the Visma Sign API.

    This class is responsible for:
    - Building signed HMAC–SHA512 requests
    - Making authenticated API calls
    - Uploading PDF files
    - Creating Visma Sign documents
    - Sending signing invitations
    - Fetching invitation and signing statuses
    - Downloading signed files
    - Logging all API traffic into vismasign.binding
    """

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
        """
        Ensure the base URL does not end with a trailing slash.

        Visma Sign rejects URLs that contain a double trailing slash,
        so this prevents accidental misconfiguration.
        """
        for rec in self:
            if rec.base_url.endswith("/"):
                raise ValidationError(_("Base URL must not end with '/'."))

    def _get_secret_key(self):
        """
        Decode the Base64-encoded secret key.

        :return: Raw bytes of the secret key
        """
        return base64.b64decode(self.secret_key_b64 or "")

    def _build_headers(self, method, path, body, content_type=""):
        """
        Build the signed HMAC–SHA512 authorization headers required by Visma Sign.

        Follows Visma Sign authentication format:
            METHOD
            Base64(MD5(body))
            Content-Type
            Date
            Request-Path

        The signature is:
            Base64(HMAC_SHA512(secret_key, above_string))

        :param method: HTTP method (GET/POST)
        :param path: API endpoint path
        :param body: Raw request body in bytes
        :param content_type: MIME type of the request
        :return: Dictionary of HTTP headers
        """
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
        """
        Perform a signed HTTP request to Visma Sign API.

        Automatically signs headers using `_build_headers`.

        :param method: HTTP method
        :param path: Endpoint path
        :param body: Request body (bytes)
        :param content_type: MIME type
        :return: Response object from `requests`
        :raises UserError: On network or API errors
        """
        url = f"{self.base_url}{path}"
        headers = self._build_headers(method, path, body, content_type)
        try:
            resp = requests.request(method, url, headers=headers, data=body, timeout=30)
        except requests.RequestException as e:
            raise UserError(str(e))
        return resp

    def action_test_connection(self):
        """
        Test backend connectivity by performing a GET request to a known dummy UUID.

        Any 200 or 404 response is considered valid because:
        - 200 = existing document (unlikely but valid)
        - 404 = document not found but authentication OK

        In all cases, the request is logged into vismasign.binding.
        """
        self.ensure_one()

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
        """
        Create a new empty document container in Visma Sign.

        Endpoint:
            POST /api/v1/document/

        :param payload: Dict containing document metadata
        :return: Newly created document UUID
        :raises UserError: If the API does not return HTTP 201
        """
        self.ensure_one()
        path = "/api/v1/document/"
        body = json.dumps(payload).encode("utf-8")

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "POST",
                "endpoint": path,
                "payload": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        )

        response = self._request("POST", path, body, "application/json")

        binding.write(
            {
                "status_code": response.status_code,
                "response": response.text,
                "successful": response.status_code == 201,
            }
        )
        if response.status_code != 201:
            raise UserError(
                _("Failed to create document in Visma Sign:\n%s") % response.text
            )

        location = response.headers.get("Location")

        document_uuid = location.rstrip("/").split("/")[-1]
        return document_uuid

    def add_file(self, document_uuid, filename, pdf_data):
        """
        Upload a PDF file to an existing Visma Sign document.

        Endpoint:
            POST /api/v1/document/{uuid}/files?filename=

        :param document_uuid: Target document UUID
        :param filename: File name to show in Visma Sign
        :param pdf_data: Raw PDF bytes
        :return: File UUID assigned by Visma Sign
        :raises UserError: If upload fails or no UUID returned
        """
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

        return file_uuid

    def send_invitation(self, document_uuid, recipient_email):
        """
        Send a signing invitation to a user by email.

        Endpoint:
            POST /api/v1/document/{uuid}/invitations

        The backend sends the email via Visma Sign.

        :param document_uuid: Document UUID
        :param recipient_email: Email of the signer
        :return: Parsed JSON response
        :raises UserError: On API error
        """
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
        Get the status of a signing invitation.

        Endpoint:
            GET /api/v1/invitation/{uuid}

        Returns status values such as:
            - pending
            - opened
            - signed
            - expired
            - rejected

        :param invitation_uuid: Invitation UUID
        :return: Parsed JSON response
        :raises UserError: If API does not return 200 OK
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

        return data

    def get_document_file(self, document_uuid, index=0):
        """
        Download a file attached to a Visma Sign document.

        Endpoint:
            GET /api/v1/document/{uuid}/files/{index}

        :param document_uuid: Document UUID
        :param index: File index, default is 0
        :return: Binary file content (PDF)
        :raises UserError: If download fails
        """
        self.ensure_one()
        path = f"/api/v1/document/{document_uuid}/files/{index}"

        binding = self.env["vismasign.binding"].create(
            {
                "backend_id": self.id,
                "method": "GET",
                "endpoint": path,
            }
        )

        response = self._request("GET", path)

        if response.status_code != 200:
            try:
                response_text = response.text
            except Exception:
                response_text = "<binary response>"

            binding.write(
                {
                    "status_code": response.status_code,
                    "response": response_text,
                    "successful": False,
                }
            )

            raise UserError(
                _("Visma Sign get document file failed: %s\n%s")
                % (response.status_code, response_text)
            )

        content = response.content or b""
        content_length = len(content)

        binding.write(
            {
                "status_code": response.status_code,
                "response": _("Binary content (%s bytes)") % content_length,
                "successful": True,
            }
        )

        return content
