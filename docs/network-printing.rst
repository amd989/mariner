Network Printing
================

Mariner can receive files and commands from external slicer tools over the
network. This lets you send a sliced model directly from your desktop to the
printer without opening the Mariner web interface.

The feature is built on a **provider** system: each supported tool gets its own
set of HTTP endpoints that speak the protocol the tool expects. Providers are
always active and require no server-side configuration.

.. contents:: On this page
   :local:
   :depth: 2


Supported Providers
-------------------

UVTools
~~~~~~~

`UVTools <https://github.com/sn4k3/UVtools>`_ is a popular MSLA/DLP slicer
utility with built-in support for sending files to remote printers. Mariner
exposes a set of endpoints that UVTools can talk to natively.

Configuring UVTools
^^^^^^^^^^^^^^^^^^^

1. Open **UVTools > Settings > Network**.
2. Click the **+** button to add a new remote printer.
3. Fill in the fields:

   :Name: Any label you like (e.g. ``Mariner``).
   :Host: The IP address or hostname of your Mariner instance.
   :Port: The port Mariner listens on (default ``5050``).
   :Extensions: ``ctb;cbddlp;fdg;photon``

4. Configure each operation as shown in the table below.
5. Toggle **Status** to **Enabled** and click **Save**.

.. list-table:: UVTools operation mapping
   :header-rows: 1
   :widths: 20 10 30

   * - Operation
     - Method
     - Request path
   * - UploadFile
     - ``POST``
     - ``uvtools/upload/{0}``
   * - PrintFile
     - ``GET``
     - ``uvtools/print/{0}``
   * - DeleteFile
     - ``GET``
     - ``uvtools/delete/{0}``
   * - PausePrint
     - ``GET``
     - ``uvtools/pause``
   * - ResumePrint
     - ``GET``
     - ``uvtools/resume``
   * - StopPrint
     - ``GET``
     - ``uvtools/stop``
   * - GetFiles
     - ``GET``
     - ``uvtools/files``
   * - PrintStatus
     - ``GET``
     - ``uvtools/status``
   * - PrinterInfo
     - ``GET``
     - ``uvtools/info``

``{0}`` is a placeholder that UVTools replaces with the filename at request
time.

.. note::
   ``PUT`` also works for UploadFile if you prefer it. The PausePrint,
   ResumePrint, and StopPrint paths optionally accept a trailing ``/{0}``
   (e.g. ``uvtools/pause/{0}``); the filename is accepted but ignored for
   those operations.

Using it
^^^^^^^^

Once configured, open a sliced file in UVTools and use **File > Send To >
<your printer name>**. UVTools uploads the file directly to Mariner's file
storage. Hold **Shift** while clicking the menu item to upload *and*
immediately start printing.

You can also use the other operations (pause, resume, stop) from the same
menu when a print is running.


How it works
------------

Each provider registers a Flask blueprint under its own URL prefix
(``/uvtools/`` for the UVTools provider). These endpoints translate between
the external tool's protocol and Mariner's internal printer and file
management code.

Provider routes are exempt from CSRF protection so that headless HTTP clients
can call them without needing a browser session.

Uploaded files go to the same directory that the Mariner web UI uses
(``/mnt/usb_share`` by default), so they appear in both the web file browser
and on the printer's USB drive.


Adding more providers
---------------------

The provider system is designed to be extended. To add support for a new tool:

1. Create a new module in ``mariner/server/providers/`` (e.g.
   ``myapp.py``).
2. Subclass ``NetworkPrintProvider`` and implement the ``name`` property and
   ``register_routes()`` method.
3. Add an instance of your provider to the ``_providers`` list in
   ``mariner/server/providers/__init__.py``.

The provider's routes are automatically registered with CSRF exemption and
excluded from the SPA fallback. See the UVTools provider for a reference
implementation.
