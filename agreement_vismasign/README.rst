.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

===================
Agreement vismasign
===================
This module integrates the **Agreement** application with the
generic **Visma Sign Connector**.

It builds upon the reusable connector backend and implements the **business flow**
for sending agreements to Visma Sign, uploading the PDF, sending invitations,
and tracking signing status.

Features
========

* Automatically sends every new Agreement to Visma Sign
* Generates a PDF report for each agreement
* Creates a Visma Sign document
* Uploads the PDF file
* Sends a signing invitation to the partner email
* Stores returned UUIDs on the Agreement record:

  - ``vismasign_document_uuid``
  - ``vismasign_file_uuid``
  - ``vismasign_invitation_uuid``

* Tracks status on the agreement using:

  - ``vismasign_status``
  - ``vismasign_last_check``

* Includes a scheduled cron job that updates the invitation status every 15 minutes


Configuration
=============

1. Install the **Visma Sign Connector** module.
2. Configure at least one Visma Sign backend.
3. Install this module.
4. Ensure the agreement report template is correct for your use case.

Usage
=====
* Create a new Agreement → it is automatically sent to Visma Sign.
* Check the following fields on the Agreement:

  - **Visma Sign Document UUID**
  - **Visma Sign File UUID**
  - **Visma Sign Invitation UUID**
  - **Visma Sign Status**

* The cron task keeps the status up to date.

Known issues / Roadmap
======================
\-

Credits
=======

Contributors
------------

* Valtteri Lattu <valtteri.lattu@futural.fi>

Maintainer
----------

.. image:: https://tawasta.fi/templates/tawastrap/images/logo.png
   :alt: Oy Tawasta OS Technologies Ltd.
   :target: https://tawasta.fi/

This module is maintained by Oy Tawasta OS Technologies Ltd.
