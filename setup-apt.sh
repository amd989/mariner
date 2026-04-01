#!/bin/bash
set -e
echo "Adding Mariner 2 APT repository..."
curl -fsSL https://amd989.github.io/mariner/gpg.key | gpg --dearmor -o /usr/share/keyrings/mariner3d.gpg
echo "deb [signed-by=/usr/share/keyrings/mariner3d.gpg] https://amd989.github.io/mariner stable main" > /etc/apt/sources.list.d/mariner3d.list
apt-get update
echo "Done! Run: sudo apt install mariner3d"
