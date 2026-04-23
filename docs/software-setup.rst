Software Setup
==============

Once your :doc:`hardware setup <hardware-setup>` done, you will have to:

1. Install Mariner 2
2. Setup the `USB Gadget driver
   <https://www.kernel.org/doc/html/latest/driver-api/usb/gadget.html>`_ so that
   the printer can see uploaded files
3. Enable the serial port so the Raspberry Pi can send commands to the printer

This section will guide you through those steps.

Installing Mariner 2
--------------------

There are several ways to install Mariner 2 depending on your platform.

Debian / Ubuntu / Raspberry Pi OS (apt)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Published ``.deb`` packages are built per Debian release codename (currently
**bookworm** and **trixie**). The install script selects the matching suite from
``/etc/os-release`` (``VERSION_CODENAME``). Pure **Ubuntu** releases use their
own codenames (for example ``noble``); those are not published here unless they
match a supported suite—use Docker, the RPM instructions below, or a
Debian-bookworm/trixie-based image (many **Raspberry Pi OS** releases do).

The APT repository also publishes a **stable** suite that carries the same
packages as **bookworm**, so older ``sources.list`` lines that still use
``stable`` keep working. **Trixie** machines should use the ``trixie`` suite (or
re-run ``setup.sh``) so they install the build that matches their Python stack.

First, enable the repository:

.. code-block:: shell-session

   $ curl -fsSL https://amd989.github.io/mariner/setup.sh | sudo bash

Then install mariner:

.. code-block:: shell-session

   $ sudo apt install mariner3d

On Debian-derived systems without a supported codename, the script exits with an
error; use Docker or install from source until a build exists for your suite.

Or set up the repository manually (replace ``CODENAME`` with ``bookworm`` or
``trixie``, matching your distro):

.. code-block:: shell-session

   $ curl -fsSL https://amd989.github.io/mariner/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/mariner3d.gpg
   $ CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
   $ echo "deb [signed-by=/usr/share/keyrings/mariner3d.gpg] https://amd989.github.io/mariner ${CODENAME} main" | sudo tee /etc/apt/sources.list.d/mariner3d.list
   $ sudo apt update
   $ sudo apt install mariner3d

Rocky Linux / RHEL / Fedora (dnf)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Quick install:

.. code-block:: shell-session

   $ curl -fsSL https://amd989.github.io/mariner/setup-rpm.sh | sudo bash
   $ sudo dnf install mariner3d

Or set up the repository manually:

.. code-block:: shell-session

   $ sudo rpm --import https://amd989.github.io/mariner/gpg.key
   $ sudo tee /etc/yum.repos.d/mariner3d.repo <<EOF
   [mariner3d]
   name=Mariner 2 - MSLA 3D Printer Controller
   baseurl=https://amd989.github.io/mariner/rpm/
   enabled=1
   gpgcheck=1
   gpgkey=https://amd989.github.io/mariner/gpg.key
   EOF
   $ sudo dnf install mariner3d

Docker
~~~~~~

Mariner 2 is available as a multi-architecture Docker image:

.. code-block:: shell-session

   $ docker run -d \
       --name mariner \
       --device /dev/ttyUSB0 \
       -v /mnt/usb_share:/mnt/usb_share \
       -p 5000:5000 \
       amd989/mariner3d

The image is also available from GitHub Container Registry:

.. code-block:: shell-session

   $ docker pull ghcr.io/amd989/mariner

.. note::
   When using Docker, you still need to configure the USB Gadget and serial
   port on the host system as described below. Pass the serial device and USB
   share volume into the container.

Automated setup
---------------

The package ships a helper script that performs all of the boot-partition,
USB gadget, and serial port steps described in the rest of this page.
It works on **Raspberry Pi OS** and **Armbian**:

.. code-block:: shell-session

   $ sudo mariner3d-setup-pi

The script is idempotent — safe to re-run — and backs up each file it edits
to ``<file>.mariner.bak`` on the first run.

On Raspberry Pi OS it auto-detects your Pi model (using ``dr_mode=peripheral``
where needed) and the boot partition location (``/boot`` vs ``/boot/firmware``
on Bookworm and newer).

On Armbian it configures ``/boot/armbianEnv.txt`` instead and adds an
``/etc/fstab`` entry for the USB container file.

Useful flags:

.. code-block:: shell-session

   $ sudo mariner3d-setup-pi --size 4096   # 4 GB container instead of 2 GB
   $ sudo mariner3d-setup-pi --dry-run     # show changes without applying
   $ sudo mariner3d-setup-pi --help

Once it finishes, reboot and skip ahead to :doc:`wrapping-up`. The remaining
sections on this page document the same steps manually, in case you prefer to
run them yourself.

.. note::
   The package includes a ``mariner-usb-gadget.service`` systemd unit that
   handles loading ``g_mass_storage`` at boot. If you previously followed the
   manual instructions and used ``/etc/rc.local``, you can remove the
   ``modprobe g_mass_storage`` line from it — the unit handles that now.

USB Gadget Setup
----------------

In order to make the printer see the files uploaded to mariner, we need to
setup the `USB Gadget driver
<https://www.kernel.org/doc/html/latest/driver-api/usb/gadget.html>`_ as a Mass
Storage device. This section will guide you through that process.

Raspberry Pi OS
~~~~~~~~~~~~~~~

Enable the USB gadget driver by adding a line to ``/boot/config.txt`` (or
``/boot/firmware/config.txt`` on Bookworm and newer).

For a Pi Zero W or Pi 4B:

.. code-block:: text

   dtoverlay=dwc2

For a Pi 3A+, the port requires explicit peripheral mode since it does not
support auto-sensing OTG:

.. code-block:: text

   dtoverlay=dwc2,dr_mode=peripheral

Enable the dwc2 kernel module by adding the following to ``/boot/cmdline.txt``
just after ``rootwait``:

.. code-block:: text

   modules-load=dwc2

Armbian
~~~~~~~

Add the overlay and module load to ``/boot/armbianEnv.txt``:

.. code-block:: text

   overlays=dwc2
   extraargs=modules-load=dwc2

If an ``overlays=`` or ``extraargs=`` line already exists, append the value to
it rather than adding a duplicate line.

.. note::
   USB gadget support requires OTG-capable hardware. Not all Armbian boards
   support ``dwc2`` gadget mode — check your board's documentation.

Container file and mount point
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create the FAT32 container file that the printer will see as a USB drive.
The ``count=`` value is in MB; use multiples of 1024 for whole gigabytes:

.. code-block:: shell-session

   $ sudo dd bs=1M if=/dev/zero of=/piusb.bin count=2048
   $ sudo mkdosfs /piusb.bin -F 32 -I

Create the mount point:

.. code-block:: shell-session

   $ sudo mkdir -p /mnt/usb_share

**Armbian only** — add an ``/etc/fstab`` entry so the container is mounted at
boot (replace ``<gid>`` with the numeric GID of the ``mariner`` group, which
you can find with ``getent group mariner | cut -d: -f3``):

.. code-block:: text

   /piusb.bin /mnt/usb_share vfat users,gid=<gid>,umask=002 0 2

On Raspberry Pi OS the ``mariner-usb-gadget.service`` unit handles the mount
via ``losetup`` directly; no fstab entry is needed.

Enabling the systemd unit
~~~~~~~~~~~~~~~~~~~~~~~~~

The package includes a ``mariner-usb-gadget.service`` unit that runs at boot
to set up the loop device, mount ``/piusb.bin``, and load ``g_mass_storage``.
Enable it once:

.. code-block:: shell-session

   $ sudo systemctl enable --now mariner-usb-gadget.service

After a reboot the printer should see the contents of ``/mnt/usb_share``.

Setting up the serial port
--------------------------

First, enable UART by adding this to ``/boot/config.txt``::

   enable_uart=1

In order for the Pi to communicate with the printer's mainboard over
serial, you also need to disable the Pi's console over the serial port:

.. code-block:: shell-session

   $ sudo systemctl stop serial-getty@ttyS0
   $ sudo systemctl disable serial-getty@ttyS0

Lastly, remove the console from ``cmdline.txt`` by removing this from it::

   console=serial0,115200
