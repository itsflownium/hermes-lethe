# How the demo was made

[`assets/demo/lethe-demo.mp4`](../assets/demo/lethe-demo.mp4): 76 seconds, 1920×1080, 30 fps, H.264 + AAC.

**Order:** title → Hermes Desktop (light mode) → TUI with `hermes lethe watch` beside it → classic CLI → end card.

## What's real

- Every model reply is a genuine DeepSeek V4.1 Flash response through Hermes's Nous provider.
- Every save attempt shown was really blocked by Lethe. The recording machine's `MEMORY.md` and `USER.md` were checked byte-for-byte unchanged after every take.
- **Desktop:** Hermes's own Desktop interface (`hermes webapp`) in light mode, captured as a Chrome screencast. The labels on Hermes's tool cards are Hermes's own.
- **TUI and CLI:** real `hermes chat --tui`, `hermes lethe watch` and `hermes chat` sessions, captured byte-for-byte with timestamps, then played back in xterm.js and filmed.

## What's edited

- Waits for the model are cut, and terminal typing is sped up (6×). Model output and Lethe's output play at their original speed.
- Camera zooms and pans on the Desktop footage are added in the edit.
- While the camera is on the Lethe panel, the message that was sent is shown at the top left. It's the real prompt bubble lifted from the same frame, not retyped.
- The local username is replaced with `itsflownium`, and the Desktop sessions sidebar was collapsed while recording.
- Captions are plain on-screen text. There is no narration.

## Music

An original solo-piano piece written for this film as code ([`music-piano.py`](../assets/demo/music-piano.py), numpy additive piano synthesis): left-hand broken chords under a simple right-hand melody, F major, 76 BPM, ending on a rolled Fmaj9. No samples or third-party audio.
