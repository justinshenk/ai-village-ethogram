"""Shared helpers for the AI Village shorts (text, image fx, synthesised audio, timeline, render)."""
import bisect
import hashlib
import io
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from scipy.io import wavfile
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parents[2]
OUTD = ROOT / "analysis" / "video" / "out"
TTS = OUTD / "tts"
TTS.mkdir(parents=True, exist_ok=True)
W, H, FPS, SR = 1080, 1920, 30, 48000

F_IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
F_MONO = "/System/Library/Fonts/Menlo.ttc"
F_COMIC = "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf"
F_SERIF = "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf"
F_HELV = "/System/Library/Fonts/HelveticaNeue.ttc"
_fonts = {}


def font(path, size):
    k = (path, int(size))
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, int(size))
    return _fonts[k]


# ───────────────────────────── text ─────────────────────────────
def wrap(draw, text, f, maxw):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            t = (line + " " + w).strip()
            if draw.textlength(t, font=f) <= maxw or not line:
                line = t
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def text(img, s, box=(60, 0, W - 60, H), path=F_IMPACT, size=150, fill="white", stroke=None, sfill="black",
         align="center", valign="center", spacing=1.08, min_size=24):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    while True:
        f = font(path, size)
        lines = wrap(d, s, f, x1 - x0)
        lh = size * spacing
        th = lh * len(lines)
        if (th <= y1 - y0 and all(d.textlength(l, font=f) <= x1 - x0 for l in lines)) or size <= min_size:
            break
        size = int(size * 0.92)
    sw = stroke if stroke is not None else (max(3, size // 14) if path == F_IMPACT else 0)
    y = y0 + ((y1 - y0 - th) / 2 if valign == "center" else 0)
    for l in lines:
        tw = d.textlength(l, font=f)
        x = x0 + ((x1 - x0 - tw) / 2 if align == "center" else 0)
        d.text((x, y), l, font=f, fill=fill, stroke_width=sw, stroke_fill=sfill)
        y += lh
    return img


def canvas(color=(0, 0, 0)):
    return Image.new("RGB", (W, H), color)


# ───────────────────────────── image fx ─────────────────────────────
def to_np(im):
    return np.asarray(im if isinstance(im, Image.Image) else im, dtype=np.uint8).copy()


def zoom(a, z, cx=0.5, cy=0.5):
    if abs(z - 1) < 1e-3:
        return a
    im = Image.fromarray(a)
    cw, ch = W / z, H / z
    x0 = min(max(cx * W - cw / 2, 0), W - cw)
    y0 = min(max(cy * H - ch / 2, 0), H - ch)
    return to_np(im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)))


def deepfry(a, q=10, sat=2.6):
    a = np.clip(a.astype(np.int16) + np.random.default_rng(int(a[::97, ::89].sum()) % 2**31).integers(-38, 38, a.shape), 0, 255).astype(np.uint8)
    im = Image.fromarray(a).filter(ImageFilter.UnsharpMask(6, 300, 2))
    im = ImageEnhance.Color(im).enhance(sat)
    im = ImageEnhance.Contrast(im).enhance(1.6)
    im = ImageEnhance.Sharpness(im).enhance(5)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return to_np(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def rgb_split(a, dx):
    out = a.copy()
    out[..., 0] = np.roll(a[..., 0], dx, axis=1)
    out[..., 2] = np.roll(a[..., 2], -dx, axis=1)
    return out


def slices(a, rng, n=8, amp=120):
    out = a.copy()
    for _ in range(n):
        y = rng.integers(0, H - 20)
        h = rng.integers(8, 120)
        out[y:y + h] = np.roll(out[y:y + h], rng.integers(-amp, amp), axis=1)
    return out


def shake(a, rng, amp=24):
    return np.roll(a, (rng.integers(-amp, amp), rng.integers(-amp, amp)), axis=(0, 1))


def scanlines(a, strength=0.22):
    out = a.astype(np.float32)
    out[::4] *= 1 - strength
    return out.clip(0, 255).astype(np.uint8)


def mirror(a):
    out = a.copy()
    out[:, W // 2:] = a[:, :W // 2][:, ::-1][:, : W - W // 2]
    return out


def posterize(a, levels=4):
    step = 256 // levels
    return (a // step * step).astype(np.uint8)


def pixelate(a, k=24):
    im = Image.fromarray(a).resize((W // k, H // k), Image.NEAREST).resize((W, H), Image.NEAREST)
    return to_np(im)


def punch(t, amount=0.28, dur=0.14):
    return 1 + amount * max(0.0, 1 - t / dur) ** 2


# ───────────────────────────── audio ─────────────────────────────
def tts(s, voice="Daniel", rate=None, tempo=1.0):
    key = hashlib.md5(f"{voice}|{rate}|{tempo}|{s}".encode()).hexdigest()[:14]
    wav = TTS / f"{key}.wav"
    if not wav.exists():
        aiff = TTS / f"{key}.aiff"
        cmd = ["say", "-v", voice, "-o", str(aiff)] + (["-r", str(rate)] if rate else []) + [s]
        subprocess.run(cmd, check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-af", f"atempo={tempo}", "-ac", "1", "-ar", str(SR), str(wav)], check=True)
        aiff.unlink()
    _, x = wavfile.read(wav)
    x = x.astype(np.float32) / 32768
    idx = np.where(np.abs(x) > 0.01)[0]
    if len(idx):
        x = x[max(0, idx[0] - 200): idx[-1] + 1200]
    return x


def speed(x, f):
    """Resample: f > 1 is higher and faster."""
    n = int(len(x) / f)
    return np.interp(np.arange(n) * f, np.arange(len(x)), x).astype(np.float32)


def stutter(x, seg, n):
    k = int(seg * SR)
    piece = x[:k] * np.minimum(1, np.linspace(0, 40, k)) * np.minimum(1, np.linspace(40, 0, k))
    return np.concatenate([piece] * n + [x])


def bitcrush(x, bits=5, hold=4):
    y = np.round(x * 2 ** bits) / 2 ** bits
    return np.repeat(y[::hold], hold)[: len(x)]


def echo(x, delay=0.11, fb=0.45, n=4):
    d = int(delay * SR)
    out = np.zeros(len(x) + d * n, np.float32)
    for i in range(n + 1):
        out[i * d: i * d + len(x)] += x * fb ** i
    return out


def lowpass(x, fc):
    a = math.exp(-2 * math.pi * fc / SR)
    return lfilter([1 - a], [1, -a], x).astype(np.float32)


def highpass(x, fc):
    return (x - lowpass(x, fc)).astype(np.float32)


def tt(d):
    return np.arange(int(d * SR)) / SR


def osc(freq, d, kind="sine", duty=0.5):
    t = tt(d)
    f = np.broadcast_to(freq, t.shape) if np.ndim(freq) else np.full(t.shape, freq)
    ph = np.cumsum(f) / SR
    if kind == "sine":
        return np.sin(2 * np.pi * ph).astype(np.float32)
    if kind == "square":
        return np.where((ph % 1) < duty, 1.0, -1.0).astype(np.float32)
    if kind == "saw":
        return (2 * (ph % 1) - 1).astype(np.float32)
    raise ValueError(kind)


RNG_A = np.random.default_rng(7)


def noise(d):
    return RNG_A.uniform(-1, 1, int(d * SR)).astype(np.float32)


def boom():
    t = tt(1.1)
    f = 95 * np.exp(-t * 4) + 42
    s = osc(f, 1.1) * np.exp(-t * 3.2)
    s[:600] += noise(600 / SR) * np.linspace(1, 0, 600) * 0.6
    return np.tanh(3.2 * s) * 0.9


def airhorn():
    parts = []
    for d, gap in ((0.13, 0.05), (0.13, 0.05), (0.62, 0)):
        t = tt(d)
        s = sum(osc(f * (1 + 0.004 * np.sin(2 * np.pi * 6 * t)), d, "saw") for f in (466, 471, 233.5, 699))
        s = lowpass(s, 3200) * np.minimum(1, np.linspace(0, 30, len(t))) * np.minimum(1, np.linspace(14, 0, len(t)))
        parts += [np.tanh(1.5 * s) * 0.55, np.zeros(int(gap * SR), np.float32)]
    return np.concatenate(parts)


def sad_trombone():
    out = []
    for f, d in ((233, 0.32), (220, 0.32), (207.6, 0.32), (196, 1.1)):
        t = tt(d)
        vib = 1 + (0.02 * np.sin(2 * np.pi * 5.5 * t) * (t / d) if d > 1 else 0)
        s = lowpass(osc(f * vib, d, "saw") + 0.5 * osc(2 * f * vib, d, "saw"), 1500)
        s *= np.minimum(1, np.linspace(0, 20, len(t))) * np.minimum(1, np.linspace(6, 0, len(t)))
        out.append(s * 0.5)
    return np.concatenate(out)


def beep(f=880, d=0.11):
    return osc(f, d, "square") * 0.22 * np.minimum(1, np.linspace(30, 0, int(d * SR)))


def error_beep():
    return np.concatenate([beep(520, 0.14), np.zeros(1500, np.float32), beep(390, 0.24)])


def thud():
    t = tt(0.35)
    s = osc(70 * np.exp(-t * 6) + 45, 0.35) * np.exp(-t * 11)
    s[:2400] += lowpass(noise(2400 / SR), 2500) * np.linspace(1, 0, 2400)
    return np.tanh(2.5 * s) * 0.85


def ding():
    t = tt(1.2)
    return ((osc(1318.5, 1.2) + 0.5 * osc(1975.5, 1.2) + 0.25 * osc(2637, 1.2)) * np.exp(-t * 3.5) * 0.25).astype(np.float32)


def whoosh(d=0.45):
    n = noise(d)
    t = tt(d)
    env = np.sin(np.pi * t / d) ** 2
    lo = lowpass(n, 900)
    hi = highpass(n, 3000)
    mix = lo * (1 - t / d) + hi * (t / d)
    return (mix * env * 0.7).astype(np.float32)


def scratch(d=0.35):
    t = tt(d)
    f = 500 + 1400 * np.abs(np.sin(2 * np.pi * 3.2 * t))
    s = osc(f, d, "saw") * 0.3 + lowpass(noise(d), 2500) * 0.5
    return (s * np.sin(np.pi * t / d) * 0.8).astype(np.float32)


def drumroll(d=1.0):
    t = tt(d)
    gate = (np.sin(2 * np.pi * 26 * t) > 0.2).astype(np.float32)
    s = highpass(lowpass(noise(d), 5000), 300) * gate * (0.25 + 0.75 * t / d)
    return (s * 0.6).astype(np.float32)


def riser(d=0.8):
    t = tt(d)
    return (osc(200 * 2 ** (3 * t / d), d, "saw") * (t / d) ** 2 * 0.25).astype(np.float32)


def music(total):
    """140 bpm chip loop in A minor (Am F C G), tiled."""
    beat = 60 / 140
    bar = 4 * beat
    roots = [110.0, 87.31, 130.81, 98.0]
    triads = [(220, 261.63, 329.63), (174.61, 220, 261.63), (261.63, 329.63, 392), (196, 246.94, 293.66)]
    loop = np.zeros(int(4 * bar * SR) + SR, np.float32)

    def put(at, s, g=1.0):
        i = int(at * SR)
        loop[i:i + len(s)] += s[: len(loop) - i] * g

    for b in range(4):
        for e in range(8):
            d = beat / 2
            s = osc(roots[b], d * 0.9, "square", 0.5) * np.minimum(1, np.linspace(8, 0, int(d * 0.9 * SR)))
            put(b * bar + e * d, lowpass(s, 1400), 0.16)
        for e in range(16):
            d = beat / 4
            f = triads[b][[0, 1, 2, 1][e % 4]] * 2
            s = osc(f, d * 0.8, "square", 0.25) * np.minimum(1, np.linspace(6, 0, int(d * 0.8 * SR)))
            put(b * bar + e * d, s, 0.055)
        for k in range(4):
            t = tt(0.25)
            kick = osc(120 * np.exp(-t * 18) + 48, 0.25) * np.exp(-t * 14)
            put(b * bar + k * beat, kick, 0.55)
            if k in (1, 3):
                put(b * bar + k * beat, highpass(noise(0.15), 1200) * np.exp(-tt(0.15) * 25), 0.22)
            put(b * bar + k * beat + beat / 2, highpass(noise(0.04), 6000) * np.exp(-tt(0.04) * 80), 0.12)
    loop = loop[: int(4 * bar * SR)]
    reps = int(total * SR / len(loop)) + 2
    return np.tile(loop, reps)[: int(total * SR)]


# ───────────────────────────── data visuals ─────────────────────────────
STATE_COL = {1: (255, 140, 0), 2: (40, 120, 255), 3: (255, 215, 0), 4: (255, 0, 170), 5: (0, 220, 120)}


def build_strips():
    s = json.loads((ROOT / "analysis" / "out" / "strips.json").read_text())
    total = s["meta"]["total"]
    ag = sorted(s["agents"], key=lambda a: a["first"])
    rows = 5200
    grid = np.zeros((rows, len(ag)), np.uint8)
    for j, a in enumerate(ag):
        sg = a["segs"]
        for i in range(0, len(sg), 3):
            st, ln, state = sg[i], sg[i + 1], sg[i + 2]
            if state:
                r0 = int(st * rows / total)
                r1 = max(r0 + 1, int((st + ln) * rows / total))
                grid[r0:r1, j] = state
    img = np.full((rows, W, 3), (14, 12, 22), np.uint8)
    cw = W / len(ag)
    for j in range(len(ag)):
        x0, x1 = int(j * cw) + 1, int((j + 1) * cw) - 1
        col = grid[:, j]
        for st, c in STATE_COL.items():
            m = col == st
            img[m, x0:x1] = c
    days = s["days"]
    month_rows = {}
    for d in days:
        m = d["date"][:7]
        if m not in month_rows:
            month_rows[m] = int(d["o"] * rows / total)
    return img, month_rows


STRIPS, STRIP_MONTHS = build_strips()


def strips_view(y, dim=1.0):
    y = int(min(max(y, 0), STRIPS.shape[0] - H))
    a = STRIPS[y:y + H].copy()
    if dim != 1.0:
        a = (a * dim).astype(np.uint8)
    return a


IDLE = [("2025-04", .103), ("05", .082), ("06", .054), ("07", .019), ("08", .029), ("09", .024), ("10", .108), ("11", .048),
        ("12", .044), ("2026-01", .022), ("02", .015), ("03", .021), ("04", .073), ("05", .049), ("06", .15), ("07", .245),
        ("08", .34), ("09", .298)]

# ───────────────────────────── timeline ─────────────────────────────
class Timeline:
    def __init__(self):
        self.t = 0.0
        self.shots, self.fx, self.remap = [], [], []
        self.voice, self.sfx = [], []
        self.music_mute, self.tapestop = [], []

    def shot(self, dur, fn, start=None):
        st = self.t if start is None else start
        self.shots.append((st, dur, fn))
        return st

    def say(self, at, x, gain=1.0):
        self.voice.append((at, x, gain))
        return len(x) / SR

    def snd(self, at, x, gain=1.0):
        self.sfx.append((at, x, gain))
        return len(x) / SR

    def effect(self, t0, t1, fn):
        self.fx.append((t0, t1, fn))

    def loop(self, t0, t1, period):
        self.remap.append((t0, t1, period))

    def go(self, d):
        self.t += d


tl = Timeline()
PAL = [(255, 0, 170), (40, 120, 255), (255, 215, 0), (0, 220, 120), (255, 140, 0), (140, 60, 255)]


def slam_shot(label, bg, sub=None, fg="white", path=F_IMPACT, size=190, deep=False, strips_y=None, sub_col=(255, 255, 255)):
    def fn(t, d):
        if strips_y is not None:
            im = Image.fromarray(strips_view(strips_y + t * 300, 0.45))
        else:
            im = canvas(bg)
        text(im, label, box=(60, 520, W - 60, 1400), path=path, size=size, fill=fg)
        if sub:
            text(im, sub, box=(80, 1440, W - 80, 1600), path=F_MONO, size=46, fill=sub_col, stroke=0)
        a = zoom(to_np(im), punch(t))
        return deepfry(a) if deep else a
    return fn


def question_shot(n, q):
    def fn(t, d):
        im = canvas((6, 6, 10))
        dr = ImageDraw.Draw(im)
        dr.rectangle((70, 470, 70 + 18, 1450), fill=(255, 215, 0))
        text(im, f"QUESTION {n}", box=(130, 470, W - 60, 600), path=F_SERIF, size=90, fill=(255, 215, 0), align="left", valign="top")
        text(im, q, box=(130, 640, W - 70, 1450), path=F_IMPACT, size=150, fill="white", align="left", valign="top", stroke=0)
        a = zoom(to_np(im), 1 + 0.05 * t / max(d, 0.1), 0.35, 0.5)
        return scanlines(a, 0.18)
    return fn


def voice_slam(label, voice, s, bg=None, rate=None, sub=None, min_d=0.55, fx=None, deep=False, pitch=1.0, gain=1.0, sfx=None, **kw):
    x = tts(s, voice, rate)
    if pitch != 1.0:
        x = speed(x, pitch)
    if fx:
        x = fx(x)
    d = max(len(x) / SR + 0.06, min_d)
    tl.shot(d, slam_shot(label, bg if bg is not None else (0, 0, 0), sub=sub, deep=deep, **kw))
    tl.say(tl.t, x, gain)
    if sfx is not None:
        tl.snd(tl.t, sfx, 0.8)
    tl.go(d)
    return d


def narrate(s, rate=175, voice="Daniel"):
    x = tts(s, voice, int(rate * 1.13), tempo=1.18)
    return x, len(x) / SR



# ───────────────────────────── render ─────────────────────────────
def frame_at(t, fi):
    for a, b, p in tl.remap:
        if a <= t < b:
            t = a + ((t - a) % p)
    shot = None
    for st, d, fn in tl.shots:
        if st <= t < st + d:
            shot = (st, d, fn)
    if shot is None:
        return np.zeros((H, W, 3), np.uint8)
    st, d, fn = shot
    a = fn(t - st, d)
    a = to_np(a) if isinstance(a, Image.Image) else a
    rng = np.random.default_rng(fi)
    for a0, a1, f in tl.fx:
        if a0 <= t < a1:
            a = f(a, t, rng)
    return a


def mix(music_fn, wav_path, music_gain=0.55):
    total = tl.t
    n = int(total * SR) + SR
    voice = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    for bus, items in ((voice, tl.voice), (sfx, tl.sfx)):
        for at, x, g in items:
            i = int(at * SR)
            m = min(len(x), n - i)
            bus[i:i + m] += x[:m] * g
    mus = music_fn(n / SR)
    for a, b in tl.tapestop:
        i0, i1 = int(a * SR), int(b * SR)
        rate = np.linspace(1, 0, i1 - i0) ** 1.4
        mus[i0:i1] = np.interp(i0 + np.cumsum(rate), np.arange(len(mus)), mus)
    gain = np.ones(n, np.float32)
    for a, b in tl.music_mute:
        gain[int(a * SR):int(b * SR)] = 0
    gain = lowpass(gain, 30)
    duck = 1 - 0.75 * np.clip(lowpass(np.abs(voice), 8) * 6, 0, 1)
    out = mus * gain * duck * music_gain + voice + sfx * 0.85
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    wavfile.write(wav_path, SR, (np.stack([out, out], axis=1) * 32000).astype(np.int16))


def sheet(path, step=1.5):
    ts = np.arange(0.2, tl.t, step)
    cols, tw, th = 8, 270, 480
    S = Image.new("RGB", (cols * tw, math.ceil(len(ts) / cols) * th), (40, 40, 40))
    for k, t in enumerate(ts):
        im = Image.fromarray(frame_at(t, int(t * FPS))).resize((tw - 6, th - 30))
        x, y = (k % cols) * tw + 3, (k // cols) * th + 3
        S.paste(im, (x, y))
        ImageDraw.Draw(S).text((x + 4, y + th - 28), f"{t:.1f}s", font=font(F_MONO, 20), fill="white")
    S.save(path, quality=80)


def finish(name, music_fn):
    """CLI: --shots lists shots, --sheet writes a contact sheet, otherwise renders <name>.mp4."""
    total = tl.t
    print(f"duration {total:.1f}s, {len(tl.shots)} shots", file=sys.stderr)
    if "--shots" in sys.argv:
        for st, d, fn in tl.shots:
            print(f"  {st:6.1f} {d:5.2f} {fn.__qualname__}", file=sys.stderr)
        return
    wav = OUTD / f"{name}_mix.wav"
    mix(music_fn, wav)
    if "--sheet" in sys.argv:
        sheet(OUTD / f"{name}_sheet.jpg")
        return
    nf = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
           str(OUTD / f"{name}.mp4")]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(nf):
        p.stdin.write(frame_at(fi / FPS, fi).tobytes())
        if fi % 300 == 0:
            print(f"frame {fi}/{nf}", file=sys.stderr)
    p.stdin.close()
    p.wait()
