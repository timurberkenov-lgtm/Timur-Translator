# Timur Translator Realtime v16.3.3

macOS TLS certificate hotfix:
- Fixed `SSL: CERTIFICATE_VERIFY_FAILED` during OpenAI Realtime WebSocket connection in packaged macOS `.app` builds.
- Added the `certifi` Mozilla CA bundle to desktop dependencies.
- Explicitly passes the packaged CA file to `websocket-client` for both API preflight and the live realtime socket.
- Keeps TLS certificate verification and hostname checks enabled.
- PyInstaller now collects certifi data during Windows and macOS builds.
- Preserves the v16.3.2 macOS Appearance-button contrast fix.

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
