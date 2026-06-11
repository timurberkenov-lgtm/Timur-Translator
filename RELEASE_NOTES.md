# Timur Translator Realtime v16.3.2

macOS Appearance button rendering hotfix:
- Replaced the top `APPEARANCE` and `RESET STYLE` system buttons with custom clickable action chips.
- macOS Aqua can no longer repaint these controls with low-contrast native colors.
- `APPEARANCE` now always uses the selected accent color and automatically picks a readable light or dark label.
- Added hover styling and keyboard activation for the custom chips.
- Applied the same rendering path to Windows for consistent behavior.

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
