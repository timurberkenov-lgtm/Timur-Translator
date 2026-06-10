# Timur Translator Realtime

A Windows and macOS desktop subtitle translator for online interviews, YouTube, Zoom and Google Meet.

## Ready desktop builds through GitHub Actions

This repository contains an automated builder. It produces:

- `Timur-Translator-Realtime-Windows-x64.zip` with a ready `.exe`;
- `Timur-Translator-Realtime-macOS-arm64.zip` with a ready `.app` for Apple Silicon;
- `Timur-Translator-Realtime-macOS-x64.zip` with a ready `.app` for Intel Macs.

### Build manually on GitHub

1. Open the repository on GitHub.
2. Open the **Actions** tab.
3. Select **Build desktop apps**.
4. Click **Run workflow**.
5. Wait for all jobs to finish.
6. Open the workflow run and download the artifacts.

### Publish a GitHub Release automatically

Create and push a tag such as `v1.0.0`. The same workflow builds all desktop packages and attaches them to a GitHub Release.

## Local Windows build

Run:

```text
build_windows_local.bat
```

The ready executable appears in `release/`.

## Local macOS build

Run:

```text
build_macos_local.command
```

The ready app bundle appears in `dist/`. For YouTube, Zoom, Meet or interview system audio, install BlackHole using:

```text
macos/install_blackhole_macos.command
```

## Security

Never commit an OpenAI API key. Each user enters their own key locally in the app.
