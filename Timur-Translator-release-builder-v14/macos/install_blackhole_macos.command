#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

printf '\n=== BlackHole 2ch installer for macOS system audio ===\n\n'

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer must be run on macOS."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi

brew install --cask blackhole-2ch

cat <<'TXT'

BlackHole 2ch installation requested.
Restart your Mac before using system-audio mode.

After restart:
1. Open Audio MIDI Setup.
2. Click + and choose Create Multi-Output Device.
3. Tick your headphones or Mac speakers and BlackHole 2ch.
4. Keep your real headphones / speakers as the top clock device.
5. Enable Drift Correction for BlackHole 2ch.
6. Right-click Multi-Output Device and choose Use This Device For Sound Output.
7. Start the translator and choose System audio · ... · BlackHole.
TXT

read -r -p "Press Enter to close..."
