#!/bin/bash
set -e
echo "Adding Mariner 2 YUM/DNF repository..."
rpm --import https://amd989.github.io/mariner/gpg.key
cat > /etc/yum.repos.d/mariner3d.repo <<REPOEOF
[mariner3d]
name=Mariner 2 - MSLA 3D Printer Controller
baseurl=https://amd989.github.io/mariner/rpm/
enabled=1
gpgcheck=1
gpgkey=https://amd989.github.io/mariner/gpg.key
REPOEOF
echo "Done! Run: sudo dnf install mariner3d"
