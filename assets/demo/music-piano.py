"""An original solo-piano piece for the Lethe demo, synthesised in numpy (no samples).
Left hand: broken chords. Right hand: a simple singing line. F major, 76 BPM, timed to the film's cuts."""
import numpy as np, soundfile as sf, sys
SR = 48000
BPM = 76.0; BEAT = 60 / BPM; BAR = 4 * BEAT
TOTAL = float(sys.argv[1]); OUT = sys.argv[2]
SEC = dict(desktop=float(sys.argv[3]), tui=float(sys.argv[4]), cli=float(sys.argv[5]), end=float(sys.argv[6]))
N = int((TOTAL + 6) * SR); L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(11)

def hz(m): return 440.0 * 2 ** ((m - 69) / 12)

def piano(m, dur, vel):
    """Additive piano: stretched (inharmonic) partials, three slightly detuned strings, two-stage decay,
    velocity-dependent brightness, a soft hammer thump, and damper release at the end of the note."""
    f0 = hz(m); ring = dur + 1.8; n = int(ring * SR); t = np.arange(n) / SR
    B = 0.00035 * (f0 / 261.6) ** 0.5
    bright = 0.55 + 0.9 * vel
    out = np.zeros(n)
    for k in range(1, 15):
        fk = f0 * k * np.sqrt(1 + B * k * k)
        if fk > 16000: break
        amp = (1.0 / k ** 1.25) * np.exp(-k / (3.0 * bright))
        d_fast = (1.6 + 0.55 * k) * (f0 / 261.6) ** 0.35
        d_slow = (0.35 + 0.10 * k) * (f0 / 261.6) ** 0.35
        e = 0.55 * np.exp(-t * d_fast) + 0.45 * np.exp(-t * d_slow)
        for cents in (-0.7, 0.0, 0.8):
            out += amp * e * np.sin(2 * np.pi * fk * 2 ** (cents / 1200) * t + rng.random() * 6.28) / 3
    hammer = rng.standard_normal(int(0.012 * SR)) * np.exp(-np.arange(int(0.012 * SR)) / SR * 400) * 0.04 * vel
    out[: len(hammer)] += np.convolve(hammer, np.ones(8) / 8, "same")
    out *= np.clip(np.arange(n) / (0.003 * SR), 0, 1)
    damp = np.ones(n); i = int(dur * SR); damp[i:] = np.exp(-(t[i:] - dur) * 9)
    return out * damp * vel

def note(m, start, dur, vel):
    s = piano(m, dur, vel); i = int(start * SR); j = min(N, i + len(s)); s = s[: j - i]
    pan = np.clip((m - 60) / 30, -0.7, 0.7)
    L[i:j] += s * np.cos((pan + 1) * np.pi / 4); R[i:j] += s * np.sin((pan + 1) * np.pi / 4)

# Fmaj7 | Dm7 | Bbmaj7 | Csus4 C  — left-hand broken chords (root, fifth, tenth, fifth...)
LH = [[41, 48, 57, 60, 64, 60, 57, 48], [38, 45, 53, 57, 60, 57, 53, 45],
      [34, 41, 50, 53, 57, 53, 50, 41], [36, 43, 53, 55, 60, 55, 52, 43]]
# right-hand phrases (beat offsets within the bar, midi, beats long); two variants
RH_A = [[(0, 72, 1.5), (1.5, 70, 0.5), (2, 69, 2)],
        [(0, 69, 1), (1, 72, 1), (2, 74, 1.5), (3.5, 72, 0.5)],
        [(0, 74, 2), (2, 72, 1), (3, 69, 1)],
        [(0, 67, 2.5), (2.5, 69, 0.5), (3, 72, 1)]]
RH_B = [[(0, 77, 1.5), (1.5, 76, 0.5), (2, 72, 2)],
        [(0, 74, 1), (1, 77, 1), (2, 81, 1.5), (3.5, 79, 0.5)],
        [(0, 77, 2), (2, 74, 1), (3, 72, 1)],
        [(0, 72, 1.5), (1.5, 74, 0.5), (2, 79, 2)]]

t, bar = 0.0, 0
while t < SEC["end"] - 0.01:
    c = bar % 4
    if t < SEC["desktop"]:                                   # intro: soft rolled chords only
        for k, m in enumerate([LH[c][0], LH[c][2], LH[c][3], LH[c][4]]): note(m, t + 0.05 * k, BAR * 0.95, 0.32)
    else:
        lv = 0.34 if t < SEC["tui"] else 0.40 if t < SEC["cli"] else 0.44
        for i, m in enumerate(LH[c]): note(m, t + i * BEAT / 2, BEAT * 1.6, lv * (1.0 if i == 0 else 0.78))
        phrase = RH_A if (t < SEC["tui"] or (bar // 4) % 2 == 0) else RH_B
        rv = 0.42 if t < SEC["tui"] else 0.48
        for off, m, beats in phrase[c]:
            note(m, t + off * BEAT, beats * BEAT * 0.98, rv)
            if t >= SEC["cli"]: note(m - 12, t + off * BEAT + 0.01, beats * BEAT * 0.9, rv * 0.45)  # octave doubling for the last part
    t += BAR; bar += 1

# Ending: a slow rolled Fmaj9 that rings out under the end card
end = SEC["end"]
for k, m in enumerate([29, 41, 48, 57, 60, 64, 67, 72]): note(m, end + 0.09 * k, 4.2, 0.36 if m > 50 else 0.42)

def reverb(x, seconds=2.8, seed=0):
    n = int(seconds * SR); ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / SR * 2.6); ir[0] = 0
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)] / np.sqrt(np.sum(ir ** 2))
L2, R2 = L + 0.30 * reverb(L, seed=3), R + 0.30 * reverb(R, seed=4)
out = np.stack([L2, R2], 1)[: int(TOTAL * SR)]
fi = int(0.6 * SR); out[:fi] *= np.linspace(0, 1, fi)[:, None]
fo = int(2.4 * SR); out[-fo:] *= (np.linspace(1, 0, fo) ** 1.4)[:, None]
rms = np.sqrt(np.mean(out[int(4 * SR): int((TOTAL - 4) * SR)] ** 2)); out *= 10 ** (-17 / 20) / rms
pk = np.max(np.abs(out)); out = out * (0.95 / pk) if pk > 0.95 else out
sf.write(OUT, out.astype(np.float32), SR)
print("piano", round(len(out) / SR, 2), "s  rms", round(20 * np.log10(np.sqrt(np.mean(out ** 2))), 1), "dBFS  peak", round(float(np.max(np.abs(out))), 3))
