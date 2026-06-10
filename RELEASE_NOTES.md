# Timur Translator Realtime v16.3

Verified stability release:
- Fixed setup startup crash caused by invalid Tkinter spacing.
- Pinned `START LIVE TRANSLATION` to the bottom of the setup window.
- Added scrollable setup cards for smaller screens and large UI-scale values.
- Kept the setup form fully opaque and readable while preserving configurable subtitle-overlay opacity.
- Added adaptive setup geometry for smaller Windows and macOS displays.
- Safely cancels pending Appearance Studio preview callbacks when closing the editor.
- Hardened delayed subtitle UI callbacks during shutdown and return-to-setup flows.
- Fixed GitHub Release attachment workflow with repository checkout and explicit `GH_REPO`.
- Added pre-package source verification in GitHub Actions and local builders.

## Existing features

- OpenAI Realtime live translation.
- Microphone translation mode.
- Windows WASAPI loopback for YouTube, Zoom, Meet and online interviews.
- macOS system-audio capture through BlackHole 2ch.
- Automatic headset microphone priority.
- Customizable UI, themes, opacity, setup scaling and compact overlay mode.
- Turkish language support (`Türkçe` → `tr`).

## Notes

- Each user enters their own OpenAI API key locally.
- macOS system audio requires BlackHole 2ch and a Multi-Output Device.
- Unsigned macOS builds may require right-clicking the app and selecting **Open** on first launch.
