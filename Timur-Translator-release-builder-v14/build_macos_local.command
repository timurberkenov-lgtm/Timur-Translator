#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

printf '\n================================================\n'
printf 'Timur Translator Realtime - native macOS app builder\n'
printf '================================================\n\n'

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from brew.sh and run this file again."
  exit 1
fi

brew install portaudio
python3 -m venv .buildvenv
.buildvenv/bin/python -m pip install --upgrade pip
.buildvenv/bin/python -m pip install -r macos/requirements.txt pyinstaller

rm -rf build dist release Timur-Translator-Realtime-macOS-*.zip
mkdir -p release
iconutil -c icns assets/TimurTranslator.iconset -o assets/TimurTranslator.icns

.buildvenv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name "Timur Translator Realtime" \
  --osx-bundle-identifier "com.timur.translator.realtime" \
  --icon "assets/TimurTranslator.icns" \
  --hidden-import websocket \
  --hidden-import pyaudio \
  --collect-submodules websocket \
  macos/timur_translator.py

APP="dist/Timur Translator Realtime.app"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string Timur Translator needs audio input access for microphone and BlackHole subtitle translation." "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription Timur Translator needs audio input access for microphone and BlackHole subtitle translation." "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true" "$PLIST"

codesign --force --deep --sign - "$APP"
xattr -cr "$APP" || true
ARCH="$(uname -m)"
ditto -c -k --sequesterRsrc --keepParent "$APP" "Timur-Translator-Realtime-macOS-${ARCH}.zip"

printf '\nREADY:\n  %s\n\n' "$(pwd)/Timur-Translator-Realtime-macOS-${ARCH}.zip"
printf 'For YouTube / Zoom / Meet system audio, install BlackHole using macos/install_blackhole_macos.command.\n\n'
open dist
read -r -p "Press Enter to close..."
