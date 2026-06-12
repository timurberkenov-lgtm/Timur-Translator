# Timur Translator Realtime v16.3 verification report

This release candidate was checked without real user credentials and without access to physical Windows/macOS audio hardware.

## Fixed in v16.3

- Setup window remains fully opaque and readable even when subtitle-overlay opacity is reduced.
- Setup geometry adapts to smaller displays; the primary `START LIVE TRANSLATION` button stays pinned at the bottom.
- Setup cards remain scrollable in Basic and Advanced modes.
- Appearance Studio cancels pending preview callbacks before closing.
- Delayed subtitle UI cleanup callbacks no longer target destroyed widgets.
- GitHub Release upload workflow includes repository checkout and explicit `GH_REPO`.
- GitHub Actions and local builders now run hardware-free source verification before packaging.

## Executed checks

- Python syntax compilation for Windows and macOS sources.
- Static Tkinter spacing audit for constructor values such as `pady=(10, 16)`.
- Embedded API-key scan.
- Headless Tkinter smoke tests on simulated `1366x768` and `1024x600` displays.
- Basic / Advanced setup mode switching.
- Theme switching, setup scaling, scroll behavior and pinned start-button visibility.
- Appearance Studio preview, cancel and save paths.
- Subtitle window creation, source/translation rendering, pause/resume, overlay toggle and close paths.
- PCM16 stereo downmix.
- `48 kHz → 24 kHz` resampling.
- Float loopback conversion to mono PCM16.
- Headset microphone priority and fragile WDM-KS fallback scoring.
- Fresh-audio queue behavior under backlog.
- Realtime source/translation event dispatch.
- Fake Realtime API preflight handshake.
- Fake Windows WASAPI-loopback preflight.
- Fake macOS BlackHole input selection.
- Shell syntax validation for macOS scripts.
- Builder asset/reference validation.

## Still requires real-device acceptance testing

- Real Windows microphone drivers and WASAPI loopback on the target PC.
- Real BlackHole routing on macOS.
- Live OpenAI Realtime translation with a funded API account.
- Native `.exe` and `.app` packaging through GitHub Actions runners.


## v16.4.1 macOS automatic headphone route

Verified without physical hardware:
- macOS Python source imports and compiles;
- Windows source still imports and compiles;
- bundled `timur_audio_router.m` passes Objective-C syntax checking with Core Audio/Foundation interface stubs;
- GitHub Actions compiles the helper with `clang -fobjc-arc -framework Foundation -framework CoreAudio`;
- PyInstaller includes the helper with `--add-binary "macos/timur_audio_router:."`;
- local macOS builder performs the same compile-and-bundle step;
- source verification asserts the helper source, aggregate-device markers and monitoring hooks are present;
- normal microphone mode remains separate from macOS system-audio routing.

Hardware-dependent validation still required on a real Mac:
- connect/disconnect wired headphones;
- connect/disconnect AirPods or a Bluetooth headset;
- confirm playback remains audible while `BlackHole 2ch` receives a non-zero peak;
- confirm the physical output restores after closing Timur Translator.
