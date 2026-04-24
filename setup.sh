#!/bin/bash
# Run as root (e.g. curl ... | sudo bash /dev/stdin --prefer-armhf)
set -e
PREFER_ARMHF=
for arg in "$@"; do
  case "$arg" in
    --prefer-armhf) PREFER_ARMHF=1 ;;
  esac
done

if [ -r /etc/os-release ]; then
  # shellcheck source=/dev/null
  . /etc/os-release
fi
CODENAME="${VERSION_CODENAME:-}"
case "$CODENAME" in
  bookworm|trixie) ;;
  "")
    echo "ERROR: VERSION_CODENAME is empty. Is this a Debian-based system with /etc/os-release?" >&2
    exit 1
    ;;
  *)
    echo "ERROR: Unsupported Debian suite '${CODENAME}'. Supported: bookworm, trixie." >&2
    exit 1
    ;;
esac

echo "Adding Mariner 2 APT repository (suite: ${CODENAME})..."
curl -fsSL https://amd989.github.io/mariner/gpg.key | gpg --dearmor -o /usr/share/keyrings/mariner3d.gpg
echo "deb [signed-by=/usr/share/keyrings/mariner3d.gpg] https://amd989.github.io/mariner ${CODENAME} main" > /etc/apt/sources.list.d/mariner3d.list

if [ -n "$PREFER_ARMHF" ]; then
  native_arch=$(dpkg --print-architecture)
  if [ "$native_arch" = arm64 ] && ! dpkg --print-foreign-architectures 2>/dev/null | grep -qx armhf; then
    echo "Warning: native arch is arm64 but armhf multiarch is not enabled. Install may fail until you run:" >&2
    echo "  sudo dpkg --add-architecture armhf && sudo apt-get update" >&2
  fi
  echo "Writing apt preferences so mariner3d resolves to armhf (not native arm64) when both are available..."
  printf '%s\n' \
    "Explanation: Prefer mariner3d armhf over arm64 on multiarch ARM systems" \
    "Package: mariner3d:arm64" \
    "Pin: version *" \
    "Pin-Priority: -1" \
    > /etc/apt/preferences.d/mariner3d-prefer-armhf
fi

apt-get update
echo ""
echo "Done."
echo "  Install:  sudo apt install mariner3d"
echo "On 64-bit ARM with armhf multiarch, apt defaults to the native arch (arm64). To force armhf:"
echo "  sudo apt install mariner3d:armhf"
echo "  or re-run this script with --prefer-armhf (writes /etc/apt/preferences.d/mariner3d-prefer-armhf)."
