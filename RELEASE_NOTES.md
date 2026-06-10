# Timur Translator Realtime Desktop v14

Desktop subtitle translator for Windows and macOS.

## Features
- OpenAI Realtime live translation.
- Microphone translation mode.
- Windows system-audio capture for YouTube, Zoom, Meet and online interviews.
- macOS system-audio capture through BlackHole 2ch.
- Automatic headset microphone priority.
- Customizable UI, opacity and compact overlay mode.
- Turkish language support (`Türkçe` → `tr`).

## Downloads
- `Timur-Translator-Realtime-Windows-x64.zip`: contains the ready Windows `.exe`.
- `Timur-Translator-Realtime-macOS-arm64.zip`: ready `.app` for Apple Silicon Macs.
- `Timur-Translator-Realtime-macOS-x64.zip`: ready `.app` for Intel Macs.

## Notes
- Each user must enter their own OpenAI API key.
- The API key is not bundled into release files.
- macOS system audio requires BlackHole 2ch and a Multi-Output Device.
- Unsigned macOS builds may require right-clicking the app and selecting **Open** on first launch.

## v16.0.0 · Setup UI redesign

- Replaced the legacy setup form with a cleaner card-based screen on Windows and macOS.
- Added Basic and Advanced setup modes.
- Added custom visual toggle switches instead of legacy checkboxes.
- Added quick theme presets directly on the setup screen.
- Added a live Appearance Studio preview for background, accent, opacity and setup UI scale.
- Added configurable setup UI scaling from 85% to 130%.
- Kept the existing realtime translation, microphone and system-audio capture pipeline unchanged.

## v16.1 Setup footer hotfix

- Pins the **START LIVE TRANSLATION** button to the bottom of the setup window.
- Makes setup cards scrollable in Advanced mode and at larger UI-scale values.
- Adds mouse-wheel scrolling on Windows and macOS.
- Keeps the working realtime audio and translation pipeline unchanged.
