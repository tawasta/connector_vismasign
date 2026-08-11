.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

===================
Agreement vismasign
===================
This module integrates the OCA ``agreement`` module with Visma Sign electronic
signatures.

The module allows sending agreements directly to Visma Sign, tracking
signature status automatically, and downloading signed PDF documents.

Features
========
* Send agreements to Visma Sign directly from the agreement form
* Generate the signed document from a configurable report action
* Store Visma Sign document, file, and invitation UUIDs on the agreement
* Automatic signature status synchronization using a scheduled action
* Download and attach the signed PDF document automatically
* Multi-company support

Configuration
=============

#. Go to
   *Agreements -> Settings*

#. Configure the following settings:

   * **Visma Sign Report**
     Technical XML-ID of the report action used to generate the PDF document.
     The base ``agreement`` module does not ship a report action, so this
     must be configured, for example using a report provided by
     ``agreement_legal`` or a custom report action.

#. Ensure that a Visma Sign backend is configured for the company.

Usage
=====

#. Open an agreement (not a template).

#. Click:

   ::

       Send for Signature

#. The module will:

   * generate the agreement PDF
   * create a Visma Sign document
   * upload the PDF
   * send the signature invitation to the partner

#. Signature status is updated automatically every 15 minutes using a cron job.

#. Once the agreement has been signed:

   * the signed PDF is downloaded automatically
   * the signed document is attached to the agreement
   * a chatter notification is posted on the agreement

Technical Details
=================

Scheduled Action
----------------

The module installs the following scheduled action:

::

    Visma Sign: Update Invitation Status (Agreements)

Default interval:

* Every 15 minutes

Agreement Fields
-----------------

The following technical fields are added to the agreement:

* ``vismasign_document_uuid``
* ``vismasign_file_uuid``
* ``vismasign_invitation_uuid``
* ``vismasign_status``
* ``vismasign_last_check``


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
