#!/bin/sh
# Mariner's packages moved to https://packages.alejandro.md.
# This script now runs the setup script there instead.
set -e
echo "Mariner's packages moved to https://packages.alejandro.md. Setting that up instead." >&2
curl -fsSL https://packages.alejandro.md/setup.sh | sh
