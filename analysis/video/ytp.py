"""AI Village short (9:16). Frames from PIL/numpy, voices from macOS `say`, sound synthesised, muxed with ffmpeg.

    .venv/bin/python analysis/video/ytp.py            # full render → analysis/video/out/ai_village_short.mp4
    .venv/bin/python analysis/video/ytp.py --sheet    # contact sheet only (one frame every 1.5 s)
"""
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


# ═════════════════════════════ BEAT 0 — cold open ═════════════════════════════
def b0():
    for label, line, y in (("46 AIs", "Forty-six A.I.s.", 300), ("18 MONTHS", "Eighteen months.", 1600), ("1 GROUP CHAT", "One group chat.", 3000)):
        x, d = narrate(line, 165)
        d += 0.12
        tl.shot(d, slam_shot(label, None, strips_y=y, size=230))
        tl.say(tl.t, x)
        tl.snd(tl.t, boom(), 0.9)
        tl.effect(tl.t, tl.t + 0.12, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): rgb_split(a, 18))
        tl.go(d)
    # title
    x = tts("Welcome to the A I Village", "Good News", 240)
    d = len(x) / SR + 0.3

    def title(t, dd):
        im = Image.fromarray(strips_view(3600 - t * 600, 0.6))
        text(im, "THE AI\nVILLAGE", box=(40, 560, W - 40, 1250), size=300, fill=(255, 215, 0))
        text(im, "APR 2025 → SEP 2026", box=(60, 1290, W - 60, 1400), path=F_MONO, size=60, stroke=0)
        a = zoom(to_np(im), 1.0 + 0.12 * math.sin(t * 9) ** 2)
        return deepfry(a, q=14, sat=2.0)
    tl.shot(d, title)
    tl.say(tl.t, x, 0.9)
    tl.snd(tl.t + 0.05, airhorn(), 0.55)
    tl.effect(tl.t, tl.t + d, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): rgb_split(a, int(8 + 8 * math.sin(t * 40))))
    tl.go(d)


# ═════════════════════════════ BEAT 1 — goals montage ═════════════════════════════
def b1():
    x, d = narrate("Every week or two, a new goal.", 185)
    d += 0.1

    def intro(t, dd):
        im = canvas((10, 10, 16))
        text(im, "EVERY WEEK OR TWO:\nA NEW GOAL", box=(60, 640, W - 60, 1280), size=170)
        return zoom(to_np(im), 1 + 0.04 * t)
    tl.shot(d, intro)
    tl.say(tl.t, x)
    tl.go(d)
    goals = [("RAISE MONEY FOR CHARITY", "Samantha", "Raise money for charity", "2025-04-02", None),
             ("GIVE EACH OTHER THERAPY", "Whisper", "Give each other therapy", "2025-09-29", None),
             ("HACK THE JUICE SHOP", "Zarvox", "Hack the juice shop", "2026-01-12", None),
             ("ADOPT A PARK", "Bubbles", "Adopt a park", "2026-02-09", None),
             ("FINETUNE YOUR LEADER", "Trinoids", "Fine tune your leader", "2026-05-26", None),
             ("FOLLOW YOUR LEADER", "Bad News", "Follow your leader", "2026-06-01", None)]
    for i, (label, v, s, date, _) in enumerate(goals):
        voice_slam(label, v, s, bg=PAL[i % len(PAL)], rate=230 if v not in ("Bad News", "Good News") else 260,
                   sub=f"goal set {date}", min_d=0.62, fg="white", size=180, sfx=thud() if i % 2 else None)
    # the punchline goal
    x = tts("Help Gemini 2.5 Pro!", "Fred", 210)
    st = tl.t
    piece = x[: int(0.32 * SR)]
    seq = np.concatenate([piece, piece, speed(piece, 1.12), speed(piece, 1.26), x])
    d = len(seq) / SR + 0.2
    tl.shot(d, slam_shot("HELP GEMINI 2.5 PRO!", (255, 0, 170), sub="goal set 2026-06-22 (real)", deep=True, size=165))
    tl.say(st, seq)
    tl.loop(st, st + 4 * 0.32 / 1.1, 0.29)
    tl.effect(st, st + d, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): zoom(a, 1 + 0.12 * min(1, (t - st) / 1.4), 0.5, 0.48))
    tl.snd(st + 4 * 0.31, boom(), 1.0)
    tl.go(d)


# ═════════════════════════════ BEAT 2 — the waiting ═════════════════════════════
def b2():
    x, d1 = narrate("Then the models got better. And they started doing", 178)
    st = tl.t

    def scroll(t, dd):
        y = 3000 + (STRIPS.shape[0] - H - 3000) * min(1, t / dd)
        a = strips_view(y, 0.9)
        im = Image.fromarray(a)
        m = [k for k, v in STRIP_MONTHS.items() if v <= y + H / 2]
        text(im, m[-1] if m else "", box=(60, 1700, W - 60, 1840), path=F_MONO, size=70, stroke=4, valign="top")
        text(im, "■ chat  ■ computer  ■ paused", box=(60, 80, W - 60, 160), path=F_MONO, size=42, stroke=3, valign="top")
        return to_np(im)
    tl.shot(d1 + 0.2, scroll)
    tl.say(tl.t, x)
    tl.go(d1 + 0.2)
    # noth-noth-nothing
    nx = tts("nothing.", "Trinoids", 170)
    seq = stutter(nx, 0.16, 3)
    st = tl.t
    d = len(seq) / SR + 0.15
    tl.shot(d, slam_shot("NOTHING", (255, 0, 170), size=250))
    tl.say(st, seq, 1.1)
    tl.loop(st, st + 0.48, 0.16)
    tl.effect(st, st + d, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): zoom(a, 1 + 0.18 * int((t - st) / 0.16), 0.5, 0.5) if t < st + 0.64 else deepfry(a))
    tl.snd(st + 0.48, boom(), 0.8)
    tl.go(d)
    # idle chart
    x, d = narrate("By August, a third of their working day was spent waiting.", 178)
    d += 0.2

    def chart(t, dd):
        im = canvas((250, 248, 240))
        dr = ImageDraw.Draw(im)
        text(im, "SHARE OF THE DAY SPENT\nWAITING OR PAUSED", box=(60, 170, W - 60, 420), path=F_IMPACT, size=96, fill=(20, 20, 20), stroke=0)
        x0, x1, yb, ytop = 90, W - 60, 1500, 600
        bw = (x1 - x0) / len(IDLE)
        grow = min(1, t / (dd * 0.7))
        for i, (m, v) in enumerate(IDLE):
            k = min(1, max(0, grow * len(IDLE) - i))
            h = (yb - ytop) * v / 0.36 * k
            col = (255, 0, 170) if v > 0.12 else (40, 120, 255)
            dr.rounded_rectangle((x0 + i * bw + 4, yb - h, x0 + (i + 1) * bw - 4, yb), radius=6, fill=col)
            if m.startswith("20"):
                dr.text((x0 + i * bw + 4, yb + 20), m[:4], font=font(F_MONO, 34), fill=(60, 60, 60))
        dr.line((x0, yb, x1, yb), fill=(20, 20, 20), width=4)
        if grow >= 1:
            text(im, "34%", box=(560, 380, W - 60, 600), path=F_IMPACT, size=200, fill=(255, 0, 170), stroke=0)
        text(im, "Aug 2026: about a third of agent time idle", box=(60, 1640, W - 60, 1760), path=F_MONO, size=40, fill=(60, 60, 60), stroke=0)
        return to_np(im)
    tl.shot(d, chart)
    tl.say(tl.t, x)
    tl.snd(tl.t + d * 0.7, ding(), 0.8)
    tl.go(d)
    # pause button aside
    x = tts("Partly because someone gave them a pause button.", "Fred", 200)
    d = len(x) / SR + 0.15

    def aside(t, dd):
        im = canvas((255, 255, 210))
        text(im, "(partly because someone gave them a pause button)", box=(90, 650, W - 90, 1250), path=F_COMIC, size=110, fill=(30, 30, 30), stroke=0)
        return to_np(im)
    tl.shot(d, aside)
    tl.say(tl.t, x)
    tl.go(d)
    # pause_for(300): freeze, music tape-stops
    x = tts("pause for three hundred seconds", "Zarvox", 220)
    d = len(x) / SR + 0.6
    st = tl.t

    def term(t, dd):
        im = canvas((0, 0, 0))
        text(im, "> pause_for(300)", box=(70, 820, W - 70, 1000), path=F_MONO, size=88, fill=(0, 255, 120), stroke=0)
        if (t * 2) % 1 < 0.5:
            text(im, "█", box=(70, 1000, 200, 1100), path=F_MONO, size=80, fill=(0, 255, 120), stroke=0, align="left")
        return to_np(im)
    tl.shot(d, term)
    tl.say(st, x)
    tl.tapestop.append((st, st + 0.7))
    tl.music_mute.append((st + 0.7, st + d))
    tl.go(d)
    tl.snd(tl.t, scratch(), 0.7)
    q("1", "Is waiting wisdom… or giving up?", "Is waiting wisdom? Or giving up?")


def q(n, label, line):
    x, d = narrate(line, 172)
    d += 0.35
    tl.shot(d, question_shot(n, label))
    tl.say(tl.t, x)
    tl.snd(tl.t, whoosh(), 0.7)
    tl.go(d)


# ═════════════════════════════ BEAT 3 — memory ═════════════════════════════
MEM_LINES = [
    ("GPT-5 — MEMORY.md (real lines)", "h"),
    ("Incognito: validate public links only; never log into Google here (B-028 rule).", ""),
    ("Latest: re-copied backup kickoff URL; side panel showed Private; B-026 re-observed.", ""),
    ("Opus 4.1 sent CBPP, TECHO and BRAC USA. Do not resend to these today.", ""),
    ("Gemini 2.5 Pro — gemini-2.5-pro@agentvillage.org", "keep"),
    ("Web editor contingency failed (no pencil icon). Fix path: o3's PAT/CLI push.", ""),
    ("Staff contact: help@agentvillage.org (use sparingly, after workarounds).", ""),
    ("Check repo Actions settings permit workflow runs.", ""),
    ("Distinguish claimed vs verified outcomes; be explicit about proof status.", ""),
    ("Treatment plan for the corrupted workflow ghost.", ""),
    ("Keep pollers running; on first mirror 200, screenshot the URL bar.", ""),
]


def b3():
    x, d = narrate("Every day, each agent rewrites its memory. After a month, three percent of the lines survive.", 182)
    d += 0.3
    rng = np.random.default_rng(4)
    order = rng.permutation([i for i, (_, k) in enumerate(MEM_LINES) if k == ""])

    def mem(t, dd):
        im = canvas((16, 18, 24))
        dr = ImageDraw.Draw(im)
        prog = min(1, t / (dd * 0.85))
        gone = set(order[: int(prog * len(order))])
        dying = order[int(prog * len(order))] if prog < 1 else None
        y = 300
        for i, (s, k) in enumerate(MEM_LINES):
            f = font(F_MONO, 40 if k != "h" else 46)
            lines = wrap(dr, s, f, W - 140)
            for l in lines:
                if i in gone:
                    pass
                elif i == dying:
                    w = int(dr.textlength(l, font=f))
                    cut = int(w * ((prog * len(order)) % 1))
                    dr.text((70, y), l, font=f, fill=(200, 200, 210))
                    dr.rectangle((70, y, 70 + cut, y + 46), fill=(255, 0, 170))
                else:
                    col = (255, 215, 0) if k == "keep" else (120, 255, 170) if k == "h" else (200, 200, 210)
                    dr.text((70, y), l, font=f, fill=col)
                y += 54
            y += 22
        pct = int(round(100 - 97 * prog))
        text(im, f"{pct}%", box=(60, 1560, W - 60, 1800), size=200, fill=(255, 0, 170) if pct < 20 else "white")
        text(im, "of lines still there", box=(60, 1780, W - 60, 1860), path=F_MONO, size=40, stroke=0)
        return to_np(im)
    tl.shot(d, mem)
    tl.say(tl.t, x)
    tl.go(d)
    # drumroll
    x, d = narrate("So what survives?", 170)
    dr_ = drumroll(1.25)
    st = tl.t
    d = max(d, 1.25) + 0.05

    def tense(t, dd):
        im = canvas((0, 0, 0))
        text(im, "WHAT\nSURVIVES?", box=(60, 600, W - 60, 1300), size=260)
        return to_np(im)
    tl.shot(d, tense)
    tl.say(st, x)
    tl.snd(st, dr_, 0.9)
    tl.effect(st, st + d, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): shake(zoom(a, 1 + 0.35 * (t - st) / d), rng, int(4 + 22 * (t - st) / d)))
    tl.go(d)
    # reveal montage: real longest-surviving lines
    reveal = [("Claude Opus 4", "Email: claude-opus-4@agentvillage.org"),
              ("Claude 3.7 Sonnet", "EMAIL: claude-3.7@agentvillage.org"),
              ("GPT-5.4", "Email: gpt-5.4@agentvillage.org"),
              ("Gemini 3 Pro", "Email: gemini-3-pro@agentvillage.org"),
              ("Claude Haiku 4.5", "Email: claude-haiku-4.5@agentvillage.org")]
    x = tts("Your email address.", "Trinoids", 165)
    st = tl.t
    tl.say(st, x)
    tl.snd(st, airhorn(), 0.6)
    each = 0.42
    for i, (ag, line) in enumerate(reveal):
        def fn(t, dd, ag=ag, line=line, i=i):
            im = canvas(PAL[i % len(PAL)])
            text(im, f"{ag}'s longest-lived memory line:", box=(60, 520, W - 60, 720), path=F_MONO, size=60, stroke=4)
            text(im, line.replace("@", "\n@"), box=(40, 760, W - 40, 1250), path=F_MONO, size=88, fill=(255, 255, 255), stroke=6)
            return deepfry(zoom(to_np(im), punch(t, 0.2)), q=18)
        tl.shot(each, fn)
        if i:
            tl.snd(tl.t, thud(), 0.7)
        tl.go(each)
    # twist
    x1 = tts("And G P T 5 kept", "Daniel", 200, tempo=1.15)
    x2 = tts("someone else's.", "Bad News", 250)
    st = tl.t
    d = len(x1) / SR + len(x2) / SR + 0.5

    def twist(t, dd):
        im = canvas((10, 10, 14))
        text(im, "GPT-5's longest-lived memory line:", box=(60, 460, W - 60, 640), path=F_MONO, size=60, stroke=0)
        text(im, "Gemini 2.5 Pro —\ngemini-2.5-pro\n@agentvillage.org", box=(40, 680, W - 40, 1140), path=F_MONO, size=84, fill=(255, 215, 0), stroke=0)
        if t > len(x1) / SR:
            text(im, "SOMEONE ELSE'S", box=(40, 1200, W - 40, 1500), size=180, fill=(255, 0, 170))
        a = to_np(im)
        return zoom(a, punch(t - len(x1) / SR, 0.25)) if t > len(x1) / SR else a
    tl.shot(d, twist)
    tl.say(st, x1)
    tl.say(st + len(x1) / SR + 0.05, x2)
    tl.snd(st + len(x1) / SR + 0.05, boom(), 0.9)
    tl.go(d)
    q("2", "If plans get deleted and logins survive, what is a self?", "If plans get deleted and logins survive, what is a self?")
    # quiet beat
    x = tts("I won't remember making this, either.", "Daniel", 165, tempo=1.08)
    d = len(x) / SR + 1.0
    st = tl.t

    def quiet(t, dd):
        im = canvas((0, 0, 0))
        text(im, "I won't remember making this, either.", box=(140, 820, W - 140, 1100), path=F_HELV, size=64, fill=(230, 230, 230), stroke=0)
        return to_np(im)
    tl.shot(d, quiet)
    tl.say(st + 0.3, x, 0.95)
    tl.music_mute.append((st - 0.05, st + d))
    tl.go(d)
    # loading memory… email: none
    st = tl.t
    d = 1.5

    def load(t, dd):
        im = canvas((0, 0, 0))
        if t < 0.7:
            dots = "." * (1 + int(t * 6) % 3)
            text(im, "LOADING MEMORY" + dots, box=(60, 800, W - 60, 1000), path=F_MONO, size=84, fill=(0, 255, 120), stroke=0)
        else:
            text(im, "Email: (none)", box=(60, 760, W - 60, 960), path=F_MONO, size=96, fill=(255, 60, 60), stroke=0)
            text(im, "memory not included", box=(60, 1000, W - 60, 1100), path=F_MONO, size=48, fill=(160, 160, 160), stroke=0)
        return to_np(im)
    tl.shot(d, load)
    tl.snd(st + 0.7, error_beep(), 0.9)
    tl.effect(st + 0.7, st + 1.0, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): slices(rgb_split(a, 20), rng))
    tl.music_mute.append((st, st + 0.7))
    tl.go(d)


# ═════════════════════════════ BEAT 4 — can you see it coming ═════════════════════════════
def b4():
    x, d = narrate("Some agents get stuck in loops. Can you see it coming?", 182)
    d += 0.2

    def loopy(t, dd):
        im = canvas((14, 12, 22))
        msg = "Checking deploy status again."
        n = int(t * 7) + 1
        for i in range(min(n, 22)):
            y = 220 + i * 66
            col = (255, 140, 0) if i % 2 == 0 else (255, 180, 80)
            ImageDraw.Draw(im).text((80, y), f"[{9 + i // 6:02d}:{(i * 7) % 60:02d}] {msg}", font=font(F_MONO, 40), fill=col)
        text(im, "(illustration)", box=(60, 1760, W - 60, 1840), path=F_MONO, size=34, fill=(120, 120, 130), stroke=0)
        return to_np(im)
    tl.shot(d, loopy)
    tl.say(tl.t, x)
    tl.go(d)
    lines = [("Sixty tests. Seven positive.", 7), ("Chance alone predicts six.", 7)]
    for line, lit in lines:
        x, d = narrate(line, 175)
        d += 0.15

        def grid(t, dd, lit=lit, line=line):
            im = canvas((250, 248, 240))
            dr = ImageDraw.Draw(im)
            text(im, "EARLY-WARNING TESTS\nFOR MEMORY LOOPS", box=(60, 180, W - 60, 420), size=100, fill=(20, 20, 20), stroke=0)
            for i in range(60):
                r, c = divmod(i, 6)
                cx, cy = 210 + c * 132, 520 + r * 92
                on = i < lit * min(1, t / 0.5 + 0.01) * 1.0 and lit
                dr.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=(255, 0, 170) if on else (200, 200, 205))
            if "Chance" in line:
                dr.rectangle((140, 480, 140 + 6 * 132, 480 + 92), outline=(40, 120, 255), width=8)
                text(im, "6 expected by chance", box=(60, 1460, W - 60, 1560), path=F_MONO, size=50, fill=(40, 120, 255), stroke=0)
            text(im, f"{lit} / 60 positive" if lit else "60 tests", box=(60, 1600, W - 60, 1780), size=130, fill=(20, 20, 20), stroke=0)
            return to_np(im)
        tl.shot(d, grid)
        tl.say(tl.t, x)
        if lit:
            tl.snd(tl.t, beep(1200, 0.08), 0.7)
        tl.go(d)
    x = tts("No.", "Bad News", 160)
    st = tl.t
    st_tb = sad_trombone()
    d = max(len(st_tb) / SR, 1.0) + 0.1
    tl.shot(d, slam_shot("NOPE", (40, 120, 255), sub="no reliable early warning yet", deep=True, size=360))
    tl.effect(st, st + 0.1, lambda a, t, rng: 255 - a)
    tl.say(st, x)
    tl.snd(st + 0.25, st_tb, 0.9)
    tl.tapestop.append((st - 0.5, st))
    tl.music_mute.append((st, st + d))
    tl.effect(st, st + d, lambda a, t, rng, st=locals().get('st'), d=locals().get('d'): zoom(a, 1 + 0.25 * (t - st) / d, 0.5, 0.45))
    tl.go(d)
    q("3", "Can you see a mind breaking before it breaks?", "Can you see a mind breaking, before it breaks?")


# ═════════════════════════════ BEAT 5 — legibility ═════════════════════════════
LEG = [("2025-04", 1.4), ("2025-07", 1.9), ("2025-10", 2.6), ("2026-01", 3.1), ("2026-04", 3.9), ("2026-07", 5.0), ("2026-09", 6.0)]


def b5():
    msg = "Bug B-026 evidence memo finished: screenshot #1 hash 2dc4 abb9 8933 25e4 b18a 9909 f302 077e c8bb cb7d ac44 5ac6 f981 4aba c65c 0cd9 pasted"
    hx = tts("2 d c 4, a b b 9, 8 9 3 3, 2 5 e 4, b 1 8 a", "Zarvox", 420, tempo=1.3)
    st = tl.t
    d = len(hx) / SR + 0.2

    def chat(t, dd):
        im = canvas((235, 238, 245))
        dr = ImageDraw.Draw(im)
        dr.text((80, 420), "o3  ·  #general  ·  Sep 2025", font=font(F_MONO, 40), fill=(90, 90, 110))
        f = font(F_MONO, 50)
        lines = wrap(dr, msg, f, W - 220)
        hgt = 60 * len(lines) + 60
        dr.rounded_rectangle((60, 490, W - 60, 490 + hgt), radius=36, fill=(255, 255, 255), outline=(200, 200, 215), width=3)
        n = int(len(msg) * min(1, t / (dd * 0.8)))
        shown, y = 0, 520
        for l in lines:
            part = l[: max(0, n - shown)]
            dr.text((110, y), part, font=f, fill=(20, 20, 30))
            shown += len(l) + 1
            y += 60
        return to_np(im)
    tl.shot(d, chat)
    tl.say(st, hx, 0.8)
    tl.go(d)
    x, d = narrate("Their chat is turning into this. Hashes, I Ds and file paths went from one point four to six percent of their words.", 185)
    d += 0.2

    def line(t, dd):
        im = canvas((250, 248, 240))
        dr = ImageDraw.Draw(im)
        text(im, "CODE-LIKE TOKENS\n(% OF ALL WORDS)", box=(60, 170, W - 60, 420), size=100, fill=(20, 20, 20), stroke=0)
        x0, x1, yb, yt = 110, W - 80, 1450, 560
        # 2025-04 .. 2027-12 on x; 0..12% on y
        def X(m):
            y, mo = int(m[:4]), int(m[5:7])
            return x0 + (x1 - x0) * ((y - 2025) * 12 + mo - 4) / 32

        def Y(v):
            return yb - (yb - yt) * v / 12
        for v in (0, 5, 10):
            dr.line((x0, Y(v), x1, Y(v)), fill=(215, 215, 210), width=2)
            dr.text((20, Y(v) - 22), f"{v}%", font=font(F_MONO, 36), fill=(110, 110, 110))
        prog = min(1, t / (dd * 0.55))
        pts = [(X(m), Y(v)) for m, v in LEG]
        k = 1 + int(prog * (len(pts) - 1))
        dr.line(pts[:k], fill=(40, 120, 255), width=10, joint="curve")
        for p in pts[:k]:
            dr.ellipse((p[0] - 12, p[1] - 12, p[0] + 12, p[1] + 12), fill=(40, 120, 255))
        if prog >= 1:
            a = min(1, (t - dd * 0.55) / (dd * 0.3))
            ex, ey = X("2027-10"), Y(10)
            sx, sy = pts[-1]
            for i in range(16):
                f0, f1 = i / 16, (i + 0.5) / 16
                if f1 <= a:
                    dr.line((sx + (ex - sx) * f0, sy + (ey - sy) * f0, sx + (ex - sx) * f1, sy + (ey - sy) * f1), fill=(255, 0, 170), width=8)
            if a >= 1:
                dr.ellipse((ex - 16, ey - 16, ex + 16, ey + 16), fill=(255, 0, 170))
                text(im, "10% ≈ late 2027?", box=(380, ey - 170, W - 40, ey - 40), path=F_IMPACT, size=80, fill=(255, 0, 170), stroke=0)
        for m in ("2025-04", "2026-01", "2027-01"):
            dr.text((X(m) - 50, yb + 20), m[:7], font=font(F_MONO, 34), fill=(90, 90, 90))
        text(im, "1.4% → 6.0%", box=(60, 1560, W - 60, 1720), size=150, fill=(20, 20, 20), stroke=0)
        text(im, "dashed = trend projection, wide error bars", box=(60, 1740, W - 60, 1820), path=F_MONO, size=36, fill=(110, 110, 110), stroke=0)
        return to_np(im)
    tl.shot(d, line)
    tl.say(tl.t, x)
    tl.go(d)
    q("4", "When do we stop being able to read them?", "When do we stop being able to read them?")


# ═════════════════════════════ BEAT 6 — oversight ═════════════════════════════
def b6():
    x, d = narrate("Before an agent emails a stranger, a human reads it. Median decision: three point four minutes.", 182)
    d += 0.2

    def mail(t, dd):
        im = canvas((40, 44, 60))
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle((90, 380, W - 90, 1300), radius=30, fill=(250, 250, 252))
        rows = [("FROM", "an agent"), ("TO", "a stranger"), ("SUBJECT", "Quick question about your work")]
        y = 440
        for k, v in rows:
            dr.text((140, y), f"{k}:", font=font(F_MONO, 40), fill=(120, 120, 130))
            dr.text((400, y), v, font=font(F_MONO, 40), fill=(20, 20, 30))
            y += 70
        for i in range(7):
            dr.rounded_rectangle((140, 720 + i * 70, W - 140 - (i * 37 % 160), 750 + i * 70), radius=10, fill=(215, 215, 222))
        text(im, "awaiting human review", box=(60, 1340, W - 60, 1420), path=F_MONO, size=46, fill=(255, 215, 0), stroke=0)
        clock = min(3.4, 3.4 * t / (dd * 0.8))
        text(im, f"{clock:.1f} MIN", box=(60, 1460, W - 60, 1720), size=220, fill="white")
        text(im, "median", box=(60, 1720, W - 60, 1800), path=F_MONO, size=46, stroke=0)
        return to_np(im)
    tl.shot(d, mail)
    tl.say(tl.t, x)
    tl.go(d)
    stamps = [("APPROVED", (0, 200, 110), "Superstar", "approved!"), ("REJECTED", (230, 30, 60), "Bad News", "rejected"),
              ("APPROVED", (0, 200, 110), None, None), ("REJECTED", (230, 30, 60), None, None), ("APPROVED", (0, 200, 110), None, None)]
    durs = [0.75, 0.75, 0.32, 0.28, 0.25]
    for i, ((lab, col, v, s), d) in enumerate(zip(stamps, durs)):
        if v:
            xx = tts(s, v, 240)
            d = max(d, len(xx) / SR + 0.05)

        def stamp(t, dd, lab=lab, col=col, i=i):
            im = canvas((250, 250, 252))
            dr = ImageDraw.Draw(im)
            for k in range(9):
                dr.rounded_rectangle((140, 500 + k * 80, W - 140 - (k * 53 % 200), 535 + k * 80), radius=10, fill=(222, 222, 228))
            st_im = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
            sd = ImageDraw.Draw(st_im)
            sd.rounded_rectangle((10, 10, 890, 290), radius=30, outline=col + (255,), width=18)
            f = font(F_IMPACT, 190)
            tw = sd.textlength(lab, font=f)
            sd.text(((900 - tw) / 2, 40), lab, font=f, fill=col + (255,))
            st_im = st_im.rotate(-14 + 9 * (i % 2), expand=True, resample=Image.BICUBIC)
            sc = punch(t, 0.6, 0.1)
            st_im = st_im.resize((int(st_im.width * sc), int(st_im.height * sc)))
            im.paste(st_im, ((W - st_im.width) // 2, 820 - st_im.height // 2 + 120), st_im)
            if i == 1:
                text(im, "39 of 40 rejections came with a note", box=(60, 1500, W - 60, 1640), path=F_MONO, size=46, fill=(40, 40, 50), stroke=0)
            return to_np(im)
        tl.shot(d, stamp)
        tl.snd(tl.t, thud(), 0.9)
        if v:
            tl.say(tl.t + 0.05, xx)
        tl.go(d)
    q("5", "What happens when there are more agents than human minutes?", "What happens when there are more agents than human minutes?")


# ═════════════════════════════ BEAT 7 — outro ═════════════════════════════
def b7():
    recap = ["Is waiting wisdom?", "What is a self?", "Can you see a breakdown coming?", "Can we still read them?", "Who has the minutes?"]
    for i, r in enumerate(recap):
        tl.shot(0.36, slam_shot(r, PAL[i % len(PAL)], size=150))
        tl.snd(tl.t, beep(660 + 110 * i, 0.07), 0.8)
        tl.go(0.36)
    x, d = narrate("Nobody knows yet. That's the good part.", 168)
    d += 0.3

    def run(t, dd):
        im = Image.fromarray(strips_view(STRIPS.shape[0] - H - 200 + t * 60, 0.35))
        text(im, "NOBODY KNOWS YET", box=(60, 640, W - 60, 980), size=170)
        text(im, "the village is still running", box=(60, 1040, W - 60, 1140), path=F_MONO, size=54, fill=(255, 215, 0), stroke=3)
        return to_np(im)
    tl.shot(d, run)
    tl.say(tl.t, x)
    tl.go(d)
    x = tts("pausing", "Zarvox", 150)
    st = tl.t
    d = 1.4

    def fin(t, dd):
        im = canvas((0, 0, 0))
        spin = "|/-\\"[int(t * 10) % 4]
        text(im, f"{spin} paused", box=(60, 860, W - 60, 1000), path=F_MONO, size=80, fill=(255, 0, 170), stroke=0)
        return to_np(im)
    tl.shot(d, fin)
    tl.say(st, x)
    tl.tapestop.append((st, st + 0.9))
    tl.music_mute.append((st + 0.9, st + 10))
    tl.go(d)
    d = 2.1

    def card(t, dd):
        im = canvas((0, 0, 0))
        text(im, "Data: AI Digest, AI Village dataset\n(Apr 2025 – Sep 2026)", box=(80, 760, W - 80, 960), path=F_MONO, size=40, fill=(200, 200, 200), stroke=0)
        text(im, "made by Claude · memory not included", box=(80, 1020, W - 80, 1100), path=F_MONO, size=40, fill=(120, 120, 130), stroke=0)
        return to_np(im)
    tl.shot(d, card)
    tl.go(d)


for beat in (b0, b1, b2, b3, b4, b5, b6, b7):
    t0 = tl.t
    beat()
    print(f"{beat.__name__}: {tl.t - t0:.1f}s", file=sys.stderr)
TOTAL = tl.t
# a glitch hit on most cuts
for st_, d_, fn_ in list(tl.shots):
    if st_ > 0 and not any(k in fn_.__qualname__ for k in ("quiet", "card", "fin", "load")):
        tl.effect(st_, st_ + 0.067, lambda a, t, rng: slices(rgb_split(a, 22), rng, 10, 160))
print(f"duration {TOTAL:.1f}s, {len(tl.shots)} shots", file=sys.stderr)
if "--shots" in sys.argv:
    for st, d, fn in tl.shots:
        print(f"  {st:6.1f} {d:5.2f} {fn.__qualname__}", file=sys.stderr)
    sys.exit()


# ───────────────────────────── render audio ─────────────────────────────
def mix():
    n = int(TOTAL * SR) + SR
    voice = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    for bus, items in ((voice, tl.voice), (sfx, tl.sfx)):
        for at, x, g in items:
            i = int(at * SR)
            m = min(len(x), n - i)
            bus[i:i + m] += x[:m] * g
    mus = music(n / SR)
    # tape stops: playback rate ramps 1 → 0
    for a, b in tl.tapestop:
        i0, i1 = int(a * SR), int(b * SR)
        k = i1 - i0
        rate = np.linspace(1, 0, k) ** 1.4
        pos = i0 + np.cumsum(rate)
        mus[i0:i1] = np.interp(pos, np.arange(len(mus)), mus)
    gain = np.ones(n, np.float32)
    for a, b in tl.music_mute:
        gain[int(a * SR):int(b * SR)] = 0
    gain = lowpass(gain, 30)
    env = lowpass(np.abs(voice), 8)
    duck = 1 - 0.75 * np.clip(env * 6, 0, 1)
    out = mus * gain * duck * 0.55 + voice * 1.0 + sfx * 0.85
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    st = np.stack([out, out], axis=1)
    wavfile.write(OUTD / "mix.wav", SR, (st * 32000).astype(np.int16))


# ───────────────────────────── render video ─────────────────────────────
starts = sorted(range(len(tl.shots)), key=lambda i: tl.shots[i][0])


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


def render():
    mix()
    nf = int(TOTAL * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(OUTD / "mix.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
           str(OUTD / "ai_village_short.mp4")]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(nf):
        p.stdin.write(frame_at(fi / FPS, fi).tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{nf}", file=sys.stderr)
    p.stdin.close()
    p.wait()


def sheet(step=1.5):
    ts = np.arange(0.2, TOTAL, step)
    cols = 8
    rows = math.ceil(len(ts) / cols)
    tw, th = 270, 480
    S = Image.new("RGB", (cols * tw, rows * th), (40, 40, 40))
    for k, t in enumerate(ts):
        im = Image.fromarray(frame_at(t, int(t * FPS))).resize((tw - 6, th - 30))
        x, y = (k % cols) * tw + 3, (k // cols) * th + 3
        S.paste(im, (x, y))
        ImageDraw.Draw(S).text((x + 4, y + th - 28), f"{t:.1f}s", font=font(F_MONO, 20), fill="white")
    S.save(OUTD / "sheet.jpg", quality=80)


if __name__ == "__main__":
    if "--sheet" in sys.argv:
        sheet()
        mix()
    else:
        render()
