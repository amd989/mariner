Network Printing
================

Mariner can receive files and commands from external slicer tools over the
network. This lets you send a sliced model directly from your desktop to the
printer without opening the Mariner web interface.

The feature is built on a **provider** system: each supported tool gets its own
endpoints speaking the protocol that tool expects. A provider either adds
routes to Mariner's own web port, or runs its own listeners when the protocol
dictates its ports. Both providers are enabled by default.

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


SDCP (ChiTuBox)
~~~~~~~~~~~~~~~

SDCP (Smart Device Control Protocol) is the protocol ChiTu network-capable
mainboards speak natively. Mariner implements the device side of **SDCP
v3.0.0**, so clients that support it (ChiTuBox among them) discover and drive
Mariner as though the printer had network support built in.

There is nothing to configure in the client: it finds the printer by
broadcasting on the local network. Slice, then use the client's send-to-printer
flow and pick the printer by name.

What it provides
^^^^^^^^^^^^^^^^

* **Discovery**: Mariner answers the ``M99999`` UDP broadcast on port 3000
  with its name, model, and mainboard ID.
* **Control channel**: a WebSocket on port 3030 at ``/websocket`` carrying
  commands, live status, and printer attributes.
* **File transfer**: chunked uploads over HTTP on port 3030, verified with
  the MD5 the client sends.

Supported commands
^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 12 40

   * - Cmd
     - Operation
   * - 0 / 1
     - Refresh status / attributes
   * - 128
     - Start printing
   * - 129 / 130 / 131
     - Pause / stop / resume printing
   * - 192
     - Change printer name (applies until restart)
   * - 255
     - Terminate an in-flight file transfer
   * - 258 / 259
     - List files / batch delete
   * - 320 / 321
     - Print history and task details, with model thumbnails

Commands for hardware Mariner cannot reach are answered honestly rather than
faked: video stream (386) reports that no camera exists, and time-lapse (387)
reports failure.

Print history
^^^^^^^^^^^^^

Mariner keeps no record of past prints on its own, so the provider builds one
by watching the printer. A task opens when a print is first observed running
and closes when the printer goes idle. Each task carries the model preview
Mariner already renders for the web interface, served from the same port as
the rest of the service, so clients that show a job history display the model
image alongside it.

History is written to disk as JSON and bounded to the most recent entries, so
it survives a restart without growing without limit.

Two things follow from history being observation driven:

* Prints started while no client is connected are not recorded, because
  status polling only runs when somebody is listening.
* Mariner cannot tell a finished print from a cancelled one over the serial
  link, so a task that reached its final layer is recorded as completed and
  anything that stopped earlier is recorded as stopped.

A task's thumbnail is left empty once its file is deleted, rather than
pointing at an address that would fail to load.

.. note::
   Mariner reads the printer over a serial link that has no notion of the
   lift/drop phases SDCP models, so an active print always reports the
   ``EXPOSURING`` sub-status. Layer progress is derived from the print file,
   matching what the web UI shows.

Configuration
^^^^^^^^^^^^^

SDCP needs no configuration, but every value can be pinned in
``config.toml``:

.. code-block:: toml

   [sdcp]
   enabled = true            # set false to turn the provider off entirely
   brand_name = "CBD"
   machine_name = "Mars 3"   # defaults to printer.display_name
   firmware_version = "V1.0.0"
   resolution = "1440x2560"  # derived from a sliced file when unset
   xyz_size = "68.04x120.96x150"
   mainboard_id = ""         # 16 hex chars; derived from the host when unset
   discovery_port = 3000
   server_port = 3030
   poll_interval_secs = 3.0
   history_enabled = true    # set false to record no print history
   history_limit = 50        # most recent tasks kept
   history_path = ""         # defaults into the cache directory

.. note::
   ``history_path`` defaults inside the cache directory, which is often
   ``/tmp`` and therefore cleared on reboot. Point it somewhere durable if
   you want print history to outlive a restart.

The mainboard ID is derived from the host's machine-id so it stays stable
across restarts, which is what lets clients remember the printer. Pin
``mainboard_id`` if you need a specific value.

.. note::
   Ports 3000 and 3030 are fixed by the protocol: clients assume them and the
   discovery reply carries no port number. If either port is already in use,
   Mariner logs an error and continues serving the web interface normally.

.. note::
   Status polling only runs while a client is connected, because it shares the
   serial link with the web interface.


How it works
------------

A provider does one of two things, depending on what its protocol demands.

Providers that can live on Mariner's own web port register a Flask blueprint
under their URL prefix (``/uvtools/``). Providers whose protocol dictates its
own ports and transports, such as SDCP with its UDP discovery and WebSocket,
start their own listeners on a background thread instead. Either way the
provider translates between the external protocol and Mariner's printer and
file management code.

Provider routes are exempt from CSRF protection so that headless HTTP clients
can call them without needing a browser session.

Uploaded files go to the same directory that the Mariner web UI uses
(``/mnt/usb_share`` by default), so they appear in both the web file browser
and on the printer's USB drive.


Adding more providers
---------------------

The provider system is designed to be extended. To add support for a new tool,
create a module under ``mariner/server/providers/``, subclass
``NetworkPrintProvider``, and add an instance to the ``_providers`` list in
``mariner/server/providers/__init__.py``.

Which methods you implement depends on how the protocol works:

* **Routes on Mariner's web port.** Implement ``register_routes()`` and add
  rules to the blueprint you are handed. It is registered under ``/<name>/``,
  exempted from CSRF, and excluded from the single-page-app fallback
  automatically. See ``providers/uvtools.py``.
* **Your own listeners.** Override ``provides_http_routes`` to return
  ``False`` and implement ``start()``, which is called once from the server
  entry point. See ``providers/sdcp/``.

``start()`` is deliberately not called at import time, so importing the app
(in tests, or under a WSGI loader) never binds a port. A provider that fails
to start is logged and skipped rather than taking the server down with it.
