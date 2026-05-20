.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

====================
Sale order vismasign
====================
This module integrates Odoo Sales with Visma Sign electronic signatures.

The module allows sending sale quotations directly to Visma Sign,
tracking signature status automatically, downloading signed PDF documents,
and optionally confirming quotations automatically after all signatures
have been completed.

Features
========
* Send sale quotations to Visma Sign directly from the sale order
* Generate the signed document from a configurable report action
* Store Visma Sign document, file, and invitation UUIDs on the sale order
* Automatic signature status synchronization using a scheduled action
* Download and attach the signed PDF document automatically
* Notify the responsible salesperson when signing is completed
* Optional automatic quotation confirmation after signing
* Optional custom ``Signed Agreement`` sale order state
* Multi-company support

Configuration
=============

#. Go to
   *Sales -> Configuration -> Settings*

#. Configure the following settings under the quotation section:

   * **Visma Sign Report**
     Technical XML-ID of the report used to generate the PDF document.

     Example:

     ::

         sale.action_report_saleorder

   * **Visma Sign Post-Sign Action**

     Select what should happen after all signatures are completed:

     * **Confirm quotation**
     * **Set quotation as signed**

#. Ensure that a Visma Sign backend is configured for the company.

Usage
=====

#. Open a quotation.

#. Click:

   ::

       Send for Signature

#. The module will:

   * generate the quotation PDF
   * create a Visma Sign document
   * upload the PDF
   * send the signature invitation to the customer

#. Signature status is updated automatically every 15 minutes using a cron job.

#. Once the quotation has been signed:

   * the signed PDF is downloaded automatically
   * the signed document is attached to the sale order
   * the responsible salesperson receives a chatter notification
   * the quotation is either:
     
     * confirmed automatically, or
     * moved to the custom ``Signed Agreement`` state

Technical Details
=================

Scheduled Action
----------------

The module installs the following scheduled action:

::

    Visma Sign: Update Invitation Status

Default interval:

* Every 15 minutes

Sale Order Fields
-----------------

The following technical fields are added to the sale order:

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
