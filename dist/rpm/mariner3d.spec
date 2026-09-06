Name:           mariner3d
Version:        %{_version}
Release:        1%{?dist}
Summary:        Web application for controlling MSLA 3D Printers
License:        MIT
URL:            https://github.com/amd989/mariner
Source0:        mariner-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  libffi-devel
BuildRequires:  openssl-devel
BuildRequires:  libxml2-devel
BuildRequires:  libxslt-devel
BuildRequires:  zlib-devel
BuildRequires:  systemd-rpm-macros

Requires:       python3 >= 3.11
Requires:       libxml2
Requires:       libxslt
Requires:       zlib

%description
Mariner 2 is a web interface for remotely controlling MSLA resin 3D printers
that use ChiTu-based controllers. It supports multiple file formats including
CTB, CBDDLP, FDG, and Photon files, with encrypted CTB support.

%prep
# Nothing to unpack — we install from the pre-built sdist

%build
# Nothing to build — sdist and frontend are pre-built

%install
# Create virtualenv and install the package from sdist
python3 -m venv %{buildroot}/opt/venvs/mariner3d
# Pin dependencies to the versions in poetry.lock first, so the shipped venv
# matches what CI tested. pip would otherwise resolve them fresh from the
# sdist metadata and pick up newer releases.
if [ -f /build/dist/requirements.txt ]; then
    %{buildroot}/opt/venvs/mariner3d/bin/pip install --no-cache-dir \
        -r /build/dist/requirements.txt
fi
%{buildroot}/opt/venvs/mariner3d/bin/pip install --no-cache-dir \
    /root/rpmbuild/SOURCES/mariner-%{version}.tar.gz

# Clean up virtualenv artifacts not needed at runtime
find %{buildroot}/opt/venvs/mariner3d -type f -name "*.pyc" -delete
find %{buildroot}/opt/venvs/mariner3d -name ".gitignore" -delete
sed -i "s|%{buildroot}||g" %{buildroot}/opt/venvs/mariner3d/bin/* \
    %{buildroot}/opt/venvs/mariner3d/pyvenv.cfg

# Install frontend assets into the virtualenv
cp -r /build/frontend/dist/ %{buildroot}/opt/venvs/mariner3d/

# Install systemd services
install -D -m 0644 /build/dist/rpm/mariner3d.service \
    %{buildroot}%{_unitdir}/mariner3d.service
install -D -m 0644 /build/dist/rpm/mariner-usb-gadget.service \
    %{buildroot}%{_unitdir}/mariner-usb-gadget.service

# Install Raspberry Pi setup helper and USB gadget scripts
install -D -m 0755 /build/dist/scripts/mariner3d-setup-pi \
    %{buildroot}%{_sbindir}/mariner3d-setup-pi
install -D -m 0755 /build/dist/scripts/gadget-start \
    %{buildroot}%{_prefix}/lib/mariner3d/gadget-start
install -D -m 0755 /build/dist/scripts/gadget-stop \
    %{buildroot}%{_prefix}/lib/mariner3d/gadget-stop

# Install default config
install -D -m 0644 /build/config.toml \
    %{buildroot}%{_sysconfdir}/mariner/config.toml

# Create /usr/bin symlink
install -d %{buildroot}%{_bindir}
ln -sf /opt/venvs/mariner3d/bin/mariner %{buildroot}%{_bindir}/mariner

%pre
# Create mariner system user if it doesn't exist
getent passwd mariner >/dev/null || \
    useradd -r -s /sbin/nologin -d /nonexistent mariner
usermod -aG dialout mariner 2>/dev/null || true

%post
%systemd_post mariner3d.service
%systemd_post mariner-usb-gadget.service

%preun
%systemd_preun mariner3d.service
%systemd_preun mariner-usb-gadget.service

%postun
%systemd_postun_with_restart mariner3d.service
%systemd_postun_with_restart mariner-usb-gadget.service

%files
%dir /opt/venvs/mariner3d
/opt/venvs/mariner3d/*
%{_bindir}/mariner
%{_sbindir}/mariner3d-setup-pi
%dir %{_prefix}/lib/mariner3d
%{_prefix}/lib/mariner3d/gadget-start
%{_prefix}/lib/mariner3d/gadget-stop
%{_unitdir}/mariner3d.service
%{_unitdir}/mariner-usb-gadget.service
%dir %{_sysconfdir}/mariner
%config(noreplace) %{_sysconfdir}/mariner/config.toml

%changelog
* Thu Aug 03 2023 Alejandro Mora <mail@alejandro.md> - 0.3.1-1
- Added dark mode
- Upgrading dependencies
- Fixed Github Actions workflows execution issues
- Fixing exceptions after starting print

* Thu Aug 03 2023 Alejandro Mora <mail@alejandro.md> - 0.3.0-1
- Added support for encrypted .ctb files
- Upgrading dependencies
- Fixed Github Actions workflows execution issues

* Sat Apr 17 2021 Luiz Ribeiro <luizribeiro@gmail.com> - 0.2.0-1
- Added support for more printers
- .cbddlp and .fdg files are now supported in addition to .ctb
- Fixed bugs related to write buffers not being flushed after file upload
- Most recently uploaded files are now listed first
- Other small bug fixes and upgrades of dependencies

* Sat Oct 17 2020 Luiz Ribeiro <luizribeiro@gmail.com> - 0.1.1-1
- Fixed bug when a non-ctb file was under /mnt/usb_share
- Allow to delete non-ctb files from /mnt/usb_share

* Sun Oct 11 2020 Luiz Ribeiro <luizribeiro@gmail.com> - 0.1.0-1
- Initial release
