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
%{buildroot}/opt/venvs/mariner3d/bin/pip install --no-cache-dir \
    /root/rpmbuild/SOURCES/mariner-%{version}.tar.gz

# Fix shebang and paths in the virtualenv (relocate from buildroot)
find %{buildroot}/opt/venvs/mariner3d -type f -name "*.pyc" -delete
sed -i "s|%{buildroot}||g" %{buildroot}/opt/venvs/mariner3d/bin/*

# Install frontend assets into the virtualenv
cp -r /build/frontend/dist/ %{buildroot}/opt/venvs/mariner3d/

# Install systemd service
install -D -m 0644 /build/dist/rpm/mariner3d.service \
    %{buildroot}%{_unitdir}/mariner3d.service

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

%preun
%systemd_preun mariner3d.service

%postun
%systemd_postun_with_restart mariner3d.service

%files
%dir /opt/venvs/mariner3d
/opt/venvs/mariner3d/*
%{_bindir}/mariner
%{_unitdir}/mariner3d.service
%dir %{_sysconfdir}/mariner
%config(noreplace) %{_sysconfdir}/mariner/config.toml

%changelog
