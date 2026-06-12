# Timur Translator Realtime v16.4.1

macOS automatic headphone-route update:
- Added a bundled Core Audio helper for macOS system-audio mode.
- Automatically creates and maintains `Timur Translator Output`, a multi-output route with the active physical output first and `BlackHole 2ch` second.
- Automatically follows AirPods, Bluetooth headsets, USB audio devices and wired headphone routes while translation is running.
- Automatically falls back to MacBook speakers when headphones disconnect.
- Restores the normal physical output when Timur Translator closes.
- Keeps the Windows WASAPI behavior unchanged.

Existing fixes retained:
- macOS SSL CA bundle handling for OpenAI Realtime WebSocket.
- Improved macOS theme contrast and custom Appearance chip.
- Polished Windows and macOS UI typography.
- Microphone and system-audio translation modes.
- Turkish language support.
