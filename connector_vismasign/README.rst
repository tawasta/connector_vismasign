.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

====================
Visma Sign Connector
====================

This module provides a **generic, standalone Visma Sign connector** that integrates
Odoo with the Visma Sign electronic signature service.

It is intentionally designed as a **reusable, model-agnostic backend**.  
You can use it as a base when implementing signature flows for any Odoo model
(e.g. agreements, sales orders, HR documents, custom models, etc.).

It handles the low-level communication, authentication, API calls, request signing
and logging—allowing other modules to focus only on business logic.

Features
========

* Generic Visma Sign backend with full Connector integration
* HMAC–SHA512 request signing and authentication headers
* Document creation
* PDF file upload
* Sending signing invitations
* Fetching invitation status
* **Downloading signed PDF documents via the API**
* Request/response logging in ``vismasign.binding`` (for debugging and audit)
* “Test Connection” tool for validating configuration
* Designed to be extended by downstream feature modules (e.g. Agreement integration)

Architecture
============

This module:
------------

* Implements a reusable Connector backend (``vismasign.backend``)
* Stores all API traffic in ``vismasign.binding`` for traceability
* Exposes Python helper methods you can call from any model:
  
  - ``create_document(payload)``
  - ``add_file(document_uuid, filename, pdf_data)``
  - ``send_invitation(document_uuid, email)``
  - ``get_invitation_status(invitation_uuid)``
  - ``get_document_file(document_uuid, index=0)``

Other modules:
--------------

Feature-specific modules should:
* Generate their PDF content
* Call backend methods
* Store returned UUIDs on the business model

This connector itself **does NOT implement any business flow**—it only provides the foundation.

Configuration
=============
1. Navigate to **Visma Sign → Backends**.
2. Create a backend and fill:

   * **Base URL** (no trailing slash)
   * **Client Identifier**
   * **Secret Key (Base64)**
   * **Company**

3. Click **Test Connection**.

Usage
=====
Other modules can import and use the connector like this:

* Find your backend:

  ``backend = env["vismasign.backend"].search([], limit=1)``

* Create a document:

  ``uuid = backend.create_document(payload)``

* Add a PDF:

  ``file_uuid = backend.add_file(uuid, filename, pdf_bytes)``

* Send an invitation:

  ``inv = backend.send_invitation(uuid, email)``

* Download a signed PDF:

  ``pdf_bytes = backend.get_document_file(uuid, index=0)``

Bindings allow you to see all requests and responses in Odoo UI for debugging.

Known issues / Roadmap
======================
\-

Credits
=======

Contributors
------------

* Valtteri Lattu <valtteri.lattu@tawasta.fi>

Maintainer
----------

.. image:: https://tawasta.fi/templates/tawastrap/images/logo.png
   :alt: Oy Tawasta OS Technologies Ltd.
   :target: https://tawasta.fi/

This module is maintained by Oy Tawasta OS Technologies Ltd.
