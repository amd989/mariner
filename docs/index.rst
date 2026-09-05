Welcome to the Mariner 2 documentation!
=======================================

Mariner 2 is a web interface for controlling MSLA 3D Printers based on `ChiTu
controllers <https://www.chitusystems.com/>`_. These are controllers commonly
used on 3D Printers by many brands such as Elegoo and Phrozen, making mariner
compatible with a wide range of printers.

|Screenshot|


Features
--------

Mariner 2 provides the following features:

- Wide range of :ref:`supported MSLA 3D printers <Supported Printers>`.
- Web interface with support for both desktop and mobile.
- Upload files to be printed through the web UI over WiFi!
- :ref:`Network printing <Network Printing>`: send files straight from your
  slicer over the network. Speaks SDCP v3.0.0, so ChiTuBox discovers and
  drives Mariner as if the printer had network support built in, plus
  native support for UVTools.
- Remotely check print status: progress, current layer, time left.
- Remotely control the printer: start prints, pause/resume and stop.
- Browse files available for printing.
- Inspect ``.ctb``, ``.cbddlp`` and ``.fdg`` files: including image preview,
  print time, slicing settings and other metadata.

.. toctree::
   :hidden:

   supported-printers
   install
   network-printing
   troubleshooting
   contributing

.. |Screenshot| image:: /_static/screenshot.png
