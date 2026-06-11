# Timur Translator Realtime v16.3.1

UI contrast hotfix:
- Improved text contrast on accent-colored buttons and pills, especially on macOS.
- Fixed low-contrast labels for `APPEARANCE`, `BASIC` / `ADVANCED`, `START LIVE TRANSLATION`, and other accent actions.
- Accent-colored controls now choose dark or light text automatically based on actual contrast.
- Applied the same contrast fix to both Windows and macOS builds for consistency.

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
