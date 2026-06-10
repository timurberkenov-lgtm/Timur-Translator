Timur Translator Realtime v12 Interview Audio for Windows
===========================================================

WHY THIS VERSION EXISTS
-----------------------
A microphone hears only sound entering the microphone. It does not directly hear
a YouTube video, Zoom call, Meet call or sound playing inside headphones.

This build adds Windows SYSTEM AUDIO capture using WASAPI loopback. It records
what Windows is playing through the currently selected speakers or headphones.

RUN
---
1. Install Python 3.13 x64 and enable "Add python.exe to PATH".
2. Run install_windows.bat once. Run it again when upgrading from an older build,
   because v12 adds SoundCard and numpy dependencies.
3. Run run_windows.bat.
4. Enter your OpenAI API key and choose the target translation language.
5. Select an AUDIO SOURCE:
   - System audio · YouTube / Zoom / Meet / interview (recommended)
   - Microphone · translate my own voice
6. Press START LIVE TRANSLATION.

ONLINE INTERVIEW MODE
---------------------
Choose System audio. Keep the interview audible in your speakers or headphones.
The app follows the active Windows playback endpoint, so when headphones become
the default Windows output it reopens loopback capture for them automatically.

System audio captures every sound played by Windows, including notifications and
other browser tabs. Close noisy apps during an interview.

MICROPHONE MODE
---------------
Choose Microphone only when you want to translate your own spoken voice.
Leave [AUTO] selected so a headset microphone is preferred when available.

IMPORTANT FEEDBACK NOTE
-----------------------
Translated voice playback is disabled automatically in System audio mode.
Otherwise the translated voice could be captured again by loopback and create a
feedback loop. Use the subtitle overlay during interviews.

UI CUSTOMIZATION
----------------
While translation is running, press STYLE.

Available controls:
- preset themes: Midnight Violet, Graphite Mint, Ocean Glass, Crimson Night, Soft Light;
- window opacity from 45% to 100%;
- transparent subtitle canvas;
- translation and original transcript font sizes;
- subtitle padding;
- always-on-top mode;
- optional original transcript;
- optional diagnostic STREAM counters;
- compact overlay mode that shows only translated subtitles.

DEBUG
-----
Run debug_windows.bat, reproduce the issue, then open:
%USERPROFILE%\.timur_translator_realtime\translator_debug.log

Never share your OpenAI API key.

TARGET LANGUAGES
----------------
Turkish is available as: Türkçe

