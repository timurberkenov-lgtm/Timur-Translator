TIMUR TRANSLATOR REALTIME · macOS BUILD KIT
===========================================

WHAT IS INCLUDED
----------------
This package contains the latest translator with:
- OpenAI Realtime subtitles;
- microphone mode;
- system-audio mode for YouTube, Zoom, Meet and online interviews;
- Turkish / Türkçe target language;
- themes, opacity, always-on-top mode and compact overlay;
- a script that builds a native Timur Translator Realtime.app on your Mac.

IMPORTANT macOS DIFFERENCE
--------------------------
Windows supports direct WASAPI loopback capture. macOS does not provide the same
built-in desktop-audio route. System-audio mode therefore reads BlackHole 2ch,
a virtual audio input. Microphone mode works without BlackHole.

QUICK START · MICROPHONE MODE
-----------------------------
1. Double-click install_macos.command.
2. Double-click run_macos.command.
3. Allow microphone access when macOS asks.
4. Select: Microphone · translate my own voice.
5. Leave AUTO selected for headset-first microphone choice.

QUICK START · YOUTUBE / ZOOM / MEET / INTERVIEW AUDIO
----------------------------------------------------
1. Double-click install_macos.command.
2. Double-click install_blackhole_macos.command.
3. Restart your Mac.
4. Open Audio MIDI Setup.
5. In the lower-left corner click +, then Create Multi-Output Device.
6. Tick your headphones or Mac speakers and BlackHole 2ch.
7. Keep your real headphones / speakers as the top clock device.
8. Enable Drift Correction for BlackHole 2ch.
9. Right-click Multi-Output Device and choose Use This Device For Sound Output.
10. Double-click run_macos.command.
11. Select: System audio · YouTube / Zoom / Meet / interview · BlackHole.
12. Play a YouTube video or start the online call.

BUILD A NATIVE .APP
-------------------
1. Complete install_macos.command first.
2. Double-click build_macos.command.
3. The result will appear here:

   dist/Timur Translator Realtime.app

BlackHole is an external audio driver. It must remain installed for system-audio
capture even after the .app has been built.

FIRST-LAUNCH macOS BLOCK
------------------------
This local build is not notarized. If macOS blocks it:
1. Right-click Timur Translator Realtime.app.
2. Choose Open.
3. Confirm Open again.

PERMISSIONS
-----------
If audio is silent:
System Settings > Privacy & Security > Microphone
Enable access for Terminal, Python or Timur Translator Realtime, depending on
which launcher you used.

LOGS
----
Double-click open_log_macos.command or open this file manually:

~/.timur_translator_realtime/translator_debug.log

FILES
-----
install_macos.command              Install PortAudio and Python dependencies
install_blackhole_macos.command    Install BlackHole 2ch for system audio
run_macos.command                  Run from Python source
debug_macos.command                Run with terminal diagnostics
build_macos.command                Build a native .app on your Mac
open_log_macos.command             Open the debug log
reset_saved_settings.command       Remove locally saved preferences
