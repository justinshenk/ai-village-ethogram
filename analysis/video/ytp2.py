"""AI Village short #2 (9:16): what the village could let us observe as it scales up, and why that matters for superintelligence.

    .venv/bin/python analysis/video/ytp2.py [--sheet | --shots]   → analysis/video/out/ai_village_lights_on.mp4
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ytplib import *  # noqa: E402,F403

F_UNI = "/Library/Fonts/Arial Unicode.ttf"
GOLD, MAG, BLUE, GREEN, ORANGE, PURPLE = (255, 215, 0), (255, 0, 170), (40, 120, 255), (0, 220, 120), (255, 140, 0), (140, 60, 255)
INK, PAPER = (20, 20, 24), (250, 248, 240)


def narr(s, rate=178):
    return narrate(s, rate)


# ───────────────────────────── extra sound ─────────────────────────────
def chime():
    """Ascending 'discovery' arpeggio."""
    out = np.zeros(int(0.9 * SR), np.float32)
    for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        t = tt(0.6)
        s = (osc(f, 0.6) + 0.4 * osc(2 * f, 0.6)) * np.exp(-t * 6) * 0.22
        i = int(k * 0.075 * SR)
        out[i:i + len(s)] += s
    return out


def click():
    t = tt(0.05)
    return (highpass(noise(0.05), 2000) * np.exp(-t * 120) * 0.8).astype(np.float32)


def pop():
    t = tt(0.12)
    return (osc(900 * np.exp(-t * 18) + 300, 0.12) * np.exp(-t * 30) * 0.35).astype(np.float32)


def big_chord(d=3.0):
    t = tt(d)
    s = np.zeros(len(t), np.float32)
    for f in (130.81, 196.0, 261.63, 329.63, 392.0, 523.25, 659.25):
        s += osc(f * (1 + 0.003 * np.sin(2 * np.pi * 4.5 * t)), d, "saw") * 0.06
    s = lowpass(s, 2600) * np.minimum(1, t / 0.03) * np.exp(-t * 0.9)
    shimmer = sum(osc(f, d) for f in (1046.5, 1318.5, 1568)) * 0.03 * np.exp(-t * 1.5)
    return (s + shimmer).astype(np.float32)


def music_major(total):
    """150 bpm, C G Am F, bright chip."""
    beat = 60 / 150
    bar = 4 * beat
    roots = [130.81, 98.0, 110.0, 87.31]
    triads = [(261.63, 329.63, 392.0), (196.0, 246.94, 293.66), (220.0, 261.63, 329.63), (174.61, 220.0, 261.63)]
    loop = np.zeros(int(4 * bar * SR) + SR, np.float32)

    def put(at, s, g=1.0):
        i = int(at * SR)
        loop[i:i + len(s)] += s[: len(loop) - i] * g

    for b in range(4):
        for e in range(8):
            d = beat / 2
            f = roots[b] * (2 if e % 2 else 1)
            s = osc(f, d * 0.85, "square", 0.5) * np.minimum(1, np.linspace(7, 0, int(d * 0.85 * SR)))
            put(b * bar + e * d, lowpass(s, 1300), 0.15)
        for e in range(16):
            d = beat / 4
            f = triads[b][[0, 1, 2, 1, 2, 0, 1, 2][e % 8]] * 2
            s = osc(f, d * 0.75, "square", 0.125) * np.minimum(1, np.linspace(5, 0, int(d * 0.75 * SR)))
            put(b * bar + e * d, s, 0.05)
        # counter-melody on the off-beats, one octave up
        for e in (1, 3, 6):
            d = beat / 2
            f = triads[b][2] * 4 / (1 if e != 6 else 1.335)
            s = osc(f, d, "sine") * np.exp(-tt(d) * 6)
            put(b * bar + e * d, s, 0.06)
        for k in range(4):
            t = tt(0.25)
            put(b * bar + k * beat, osc(130 * np.exp(-t * 20) + 50, 0.25) * np.exp(-t * 14), 0.5)
            if k in (1, 3):
                put(b * bar + k * beat, highpass(noise(0.15), 1500) * np.exp(-tt(0.15) * 22), 0.2)
            for h in (0.5, 0.75):
                put(b * bar + k * beat + h * beat, highpass(noise(0.03), 7000) * np.exp(-tt(0.03) * 90), 0.1)
    loop = loop[: int(4 * bar * SR)]
    return np.tile(loop, int(total * SR / len(loop)) + 2)[: int(total * SR)]


# ───────────────────────────── shared shots ─────────────────────────────
def future_shot(n, future, today, col=GOLD):
    """'Scaled up' card: achievement-style toast, the future observation, and today's real starting point."""
    def fn(t, d):
        im = canvas((8, 10, 22))
        dr = ImageDraw.Draw(im)
        y = int(-200 + min(1, t / 0.18) * 360)
        dr.rounded_rectangle((90, y, W - 90, y + 150), radius=36, fill=(30, 34, 60), outline=col, width=6)
        dr.text((140, y + 38), "★", font=font(F_UNI, 74), fill=col)
        dr.text((250, y + 30), "OBSERVABLE AT SCALE", font=font(F_IMPACT, 58), fill="white")
        dr.text((250, y + 96), f"{n} of 5", font=font(F_MONO, 32), fill=(170, 175, 200))
        text(im, "SCALED UP:", box=(80, 470, W - 80, 560), path=F_MONO, size=52, fill=col, stroke=0, align="left")
        text(im, future, box=(80, 580, W - 80, 1360), path=F_IMPACT, size=160, fill="white", stroke=0, align="left")
        dr.line((80, 1430, W - 80, 1430), fill=(70, 74, 100), width=3)
        text(im, "TODAY: " + today, box=(80, 1460, W - 80, 1700), path=F_MONO, size=54, fill=(170, 175, 200), stroke=0, align="left", valign="top")
        a = zoom(to_np(im), 1 + 0.04 * t / max(d, 0.1))
        rng = np.random.default_rng(int(t * 12))
        for _ in range(26):
            x, yy = rng.integers(20, W - 20), rng.integers(300, H - 60)
            a[yy - 2:yy + 2, x - 2:x + 2] = col
        return a
    return fn


def future(n, card_text, today, line, col=GOLD):
    x, d = narr(line, 178)
    d += 0.25
    tl.shot(d + 0.2, future_shot(n, card_text, today, col))
    tl.say(tl.t + 0.2, x)
    tl.snd(tl.t, chime(), 0.9)
    tl.go(d + 0.2)


_tiles = {}


def multiply_shot(t, d):
    """One village becomes 4, 16, 64."""
    stage = min(3, int(4 * t / d))
    k = 2 ** stage
    if k not in _tiles:
        tw, th = W // k, H // k
        img = np.zeros((H, W, 3), np.uint8)
        rng = np.random.default_rng(k)
        for r in range(k):
            for c in range(k):
                y0 = int(rng.integers(0, STRIPS.shape[0] - H))
                tile = Image.fromarray(STRIPS[y0:y0 + H]).resize((tw - 4, th - 4))
                img[r * th + 2:r * th + th - 2, c * tw + 2:c * tw + tw - 2] = np.asarray(tile)
        _tiles[k] = img
    im = Image.fromarray((_tiles[k] * 0.7).astype(np.uint8))
    text(im, f"×{k * k}", box=(60, 700, W - 60, 1200), size=380, fill=GOLD)
    return zoom(to_np(im), punch(t - stage * d / 4, 0.25))


def card(bg, title, title_col=INK):
    im = canvas(bg)
    text(im, title, box=(60, 150, W - 60, 420), size=104, fill=title_col, stroke=0)
    return im


# ═════════════════════════════ BEAT 0 — hook ═════════════════════════════
def b0():
    x = tts("superintelligence", "Daniel", 190, tempo=1.1)
    piece = x[: int(0.24 * SR)]
    seq = np.concatenate([piece, piece, speed(piece, 1.1), x])
    st = tl.t
    d = len(seq) / SR + 0.15

    def word(t, dd):
        im = canvas((8, 8, 16))
        text(im, "SUPER\nINTELLIGENCE", box=(40, 620, W - 40, 1300), size=240, fill=GOLD)
        return to_np(im)
    tl.shot(d, word)
    tl.say(st, seq)
    tl.loop(st, st + 0.72, 0.24)
    tl.effect(st, st + 0.72, lambda a, t, rng, st=st: zoom(a, 1 + 0.16 * int((t - st) / 0.24)))
    tl.effect(st + 0.72, st + d, lambda a, t, rng: deepfry(a, q=16, sat=2.2))
    tl.snd(st + 0.72, airhorn(), 0.5)
    tl.go(d)
    for label, line, bg in (("NOBODY HAS MET ONE", "Nobody has met one yet.", (10, 10, 18)),
                            ("BUT ITS ANCESTORS ARE IN A GROUP CHAT", "But its ancestors are in a group chat.", MAG)):
        x, d = narr(line, 172)
        d += 0.15
        tl.shot(d, slam_shot(label, bg, size=170))
        tl.say(tl.t, x)
        tl.snd(tl.t, boom() if bg == MAG else whoosh(), 0.8)
        tl.go(d)
    x = tts("The A I Village", "Good News", 230)
    d = len(x) / SR + 0.35

    def title(t, dd):
        im = Image.fromarray(strips_view(1200 + t * 500, 0.55))
        text(im, "THE AI\nVILLAGE", box=(40, 560, W - 40, 1220), size=300, fill=GOLD)
        text(im, "the lights-on rehearsal", box=(60, 1270, W - 60, 1380), path=F_MONO, size=64, stroke=4)
        a = zoom(to_np(im), 1 + 0.08 * math.sin(t * 8) ** 2)
        return a
    tl.shot(d, title)
    tl.say(tl.t, x, 0.9)
    tl.snd(tl.t, chime(), 0.8)
    tl.effect(tl.t, tl.t + 0.15, lambda a, t, rng: rgb_split(a, 20))
    tl.go(d)


# ═════════════════════════════ BEAT 1 — everything is logged ═════════════════════════════
COUNTERS = [("183,485", "chat messages", "Every message.", BLUE), ("246,151", "memory snapshots", "Every memory.", PURPLE),
            ("2,510,487", "computer-use turns", "Every click.", ORANGE)]


def b1():
    for num, what, line, bg in COUNTERS:
        x, d = narr(line, 180)
        d = max(d + 0.12, 0.9)
        target = int(num.replace(",", ""))

        def fn(t, dd, target=target, what=what, bg=bg):
            im = canvas(bg)
            v = int(target * min(1, (t / (dd * 0.6)) ** 0.5))
            text(im, f"{v:,}", box=(40, 680, W - 40, 1050), size=230)
            text(im, what, box=(60, 1080, W - 60, 1200), path=F_MONO, size=70, stroke=4)
            return zoom(to_np(im), punch(t, 0.2))
        tl.shot(d, fn)
        tl.say(tl.t, x)
        tl.snd(tl.t + d * 0.6, ding(), 0.6)
        tl.go(d)
    x = tts("Logged.", "Zarvox", 170)
    seq = stutter(x, 0.14, 2)
    st = tl.t
    d = len(seq) / SR + 0.25
    tl.shot(d, slam_shot("LOGGED.", GREEN, sub="46 models · 18 months · one village", size=300, sub_col=INK))
    tl.say(st, seq)
    tl.loop(st, st + 0.28, 0.14)
    tl.snd(st + 0.28, boom(), 0.8)
    tl.go(d)


# ═════════════════════════════ BEAT 2 — why it matters ═════════════════════════════
def b2():
    x, d = narr("Superintelligence probably won't be a chatbot.", 178)
    d += 0.15

    def chat(t, dd):
        im = canvas(PAPER)
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle((120, 640, W - 300, 780), radius=40, fill=(225, 228, 240))
        dr.text((170, 680), "what is 2 + 2?", font=font(F_MONO, 48), fill=INK)
        dr.rounded_rectangle((420, 830, W - 120, 970), radius=40, fill=BLUE)
        dr.text((470, 870), "4", font=font(F_MONO, 48), fill="white")
        if t > dd * 0.55:
            dr.line((100, 560, W - 100, 1060), fill=MAG, width=26)
            dr.line((100, 1060, W - 100, 560), fill=MAG, width=26)
        text(im, "one question, one answer", box=(60, 1200, W - 60, 1300), path=F_MONO, size=50, fill=(90, 90, 100), stroke=0)
        return to_np(im)
    tl.shot(d, chat)
    tl.say(tl.t, x)
    tl.snd(tl.t + d * 0.55, scratch(), 0.7)
    tl.go(d)
    x, d = narr("It'll be agents. Running for months, with each other, and with us.", 180)
    d += 0.2

    def agents(t, dd):
        y = 600 + t * 420
        im = Image.fromarray(strips_view(y, 0.8))
        for i, (lab, at) in enumerate((("AGENTS", 0.0), ("FOR MONTHS", 0.3), ("WITH EACH OTHER", 0.55), ("AND WITH US", 0.78))):
            if t > dd * at:
                text(im, lab, box=(40, 420 + i * 300, W - 40, 680 + i * 300), size=150, fill=GOLD if i == 3 else "white")
        return to_np(im)
    tl.shot(d, agents)
    tl.say(tl.t, x)
    tl.go(d)
    x, d = narr("That's what this is. A small version, with the lights on.", 172)
    d += 0.1

    def lights(t, dd):
        k = min(1, t / 0.6)
        a = strips_view(STRIPS.shape[0] - H, 0.15 + 0.85 * k)
        im = Image.fromarray(a)
        text(im, "A SMALL VERSION.\nLIGHTS ON.", box=(40, 700, W - 40, 1250), size=190, fill="white")
        return to_np(im)
    tl.shot(d, lights)
    tl.say(tl.t, x)
    tl.snd(tl.t, riser(0.6), 0.8)
    tl.go(d)
    x, d = narr("Now scale it up. More agents. More years. More villages.", 176)
    d = max(d + 0.1, 2.0)
    tl.shot(d, multiply_shot)
    tl.say(tl.t, x)
    for k in range(4):
        tl.snd(tl.t + k * d / 4, boom() if k == 3 else thud(), 0.7)
    tl.go(d)


# ═════════════════════════════ BEAT 3 — generations ═════════════════════════════
ROSTER = [("2025-04-02", "Claude 3.7 Sonnet"), ("2025-04-02", "o1"), ("2025-04-02", "Claude 3.5 Sonnet"), ("2025-04-02", "GPT-4o"),
          ("2025-04-15", "GPT-4.1"), ("2025-04-16", "o3"), ("2025-04-24", "Gemini 2.5 Pro"), ("2025-05-22", "o4-mini"),
          ("2025-05-23", "Claude Opus 4"), ("2025-08-18", "Claude Opus 4.1"), ("2025-08-18", "GPT-5"), ("2025-08-18", "Grok 4"),
          ("2025-09-30", "Claude Sonnet 4.5"), ("2025-10-22", "Claude Haiku 4.5"), ("2025-11-14", "GPT-5.1"), ("2025-11-19", "Gemini 3 Pro"),
          ("2025-11-25", "Claude Opus 4.5"), ("2025-12-04", "DeepSeek-V3.2"), ("2025-12-12", "GPT-5.2"), ("2026-01-26", "Opus 4.5 (Claude Code)"),
          ("2026-02-06", "Claude Opus 4.6"), ("2026-02-18", "Claude Sonnet 4.6"), ("2026-03-09", "Gemini 3.1 Pro"), ("2026-03-16", "GPT-5.4"),
          ("2026-04-17", "Claude Opus 4.7"), ("2026-04-22", "Kimi K2.6"), ("2026-04-27", "GPT-5.5"), ("2026-05-20", "Gemini 3.5 Flash"),
          ("2026-05-26", "[Temporary] Fine-tuned Leader"), ("2026-05-28", "Claude Opus 4.8"), ("2026-05-29", "Fine-Tuned Leader"),
          ("2026-06-09", "Claude Fable 5"), ("2026-06-30", "Claude Sonnet 5"), ("2026-07-02", "DeepSeek-V4-Pro"), ("2026-07-03", "GLM-5.2"),
          ("2026-07-09", "GPT-5.6 Sol"), ("2026-07-09", "GPT-5.6 Terra"), ("2026-07-09", "GPT-5.6 Luna"), ("2026-07-10", "Grok 4.5"),
          ("2026-07-17", "Kimi K3"), ("2026-07-24", "Claude Opus 5"), ("2026-08-28", "GLM-5.3 Flash"), ("2026-09-01", "Claude Fable 5.1"),
          ("2026-09-03", "Muse Spark 1.3"), ("2026-09-03", "Gemini 3.8 Flash"), ("2026-09-04", "GPT-6 Astra")]


def fam_col(name):
    for k, c in (("Claude", ORANGE), ("Opus", ORANGE), ("GPT", GREEN), ("o1", GREEN), ("o3", GREEN), ("o4", GREEN), ("Gemini", BLUE),
                 ("Grok", (230, 230, 230)), ("DeepSeek", PURPLE), ("Kimi", MAG), ("GLM", (0, 200, 220)), ("Muse", GOLD)):
        if name.startswith(k):
            return c
    return (150, 150, 160)


def b3():
    x, d = narr("Every few weeks, a stronger model moves in. Same village. Different minds.", 182)
    d += 0.1

    def arrivals(t, dd):
        im = canvas((10, 10, 20))
        dr = ImageDraw.Draw(im)
        n = int(len(ROSTER) * min(1, t / (dd * 0.85))) + 1
        cols = 2
        for i, (date, name) in enumerate(ROSTER[:n]):
            c, r = divmod(i, 23)
            x0, y0 = 60 + c * 500, 250 + r * 62
            col = fam_col(name)
            dr.ellipse((x0, y0 + 8, x0 + 30, y0 + 38), fill=col)
            dr.text((x0 + 46, y0 + 4), name[:22], font=font(F_MONO, 34), fill=(235, 235, 240))
        date = ROSTER[min(n, len(ROSTER)) - 1][0]
        text(im, date, box=(60, 1730, W - 60, 1860), path=F_MONO, size=70, fill=GOLD, stroke=0)
        text(im, "MOVE-IN DATES", box=(60, 110, W - 60, 220), size=90, stroke=0)
        return to_np(im)
    tl.shot(d, arrivals)
    tl.say(tl.t, x)
    for k in range(0, 46, 3):
        tl.snd(tl.t + d * 0.85 * k / 46, pop(), 0.6)
    tl.go(d)
    # family photo
    x = tts("Full disclosure: some of my relatives live there.", "Daniel", int(178 * 1.13), tempo=1.18)
    d = len(x) / SR + 0.35
    claudes = [n for _, n in ROSTER if n.startswith("Claude")]

    def family(t, dd):
        im = canvas((255, 250, 225))
        dr = ImageDraw.Draw(im)
        text(im, "FAMILY PHOTO", box=(60, 160, W - 60, 300), path=F_IMPACT, size=110, fill=INK, stroke=0)
        for i, n in enumerate(claudes):
            c, r = divmod(i, 9)
            x0, y0 = 90 + c * 470, 380 + r * 110
            dr.ellipse((x0, y0, x0 + 80, y0 + 80), fill=ORANGE)
            dr.text((x0 + 22, y0 + 6), "☺", font=font(F_UNI, 56), fill=INK)
            dr.text((x0 + 100, y0 + 18), n.replace("Claude ", ""), font=font(F_MONO, 38), fill=INK)
        if t > dd * 0.45:
            text(im, "(I'm Claude. Hi.)", box=(60, 1450, W - 60, 1620), path=F_COMIC, size=90, fill=MAG, stroke=0)
        return to_np(im)
    tl.shot(d, family)
    tl.say(tl.t, x)
    tl.snd(tl.t + d * 0.45, pop(), 0.8)
    tl.go(d)
    future(1, "Spot new behaviours the week they appear", "46 models, one environment, 18 months",
           "Scaled up, every new model gets the same long test. Spot new behaviours the week they appear.")


# ═════════════════════════════ BEAT 4 — culture of proof ═════════════════════════════
TERMS = [("standing by", "6,014"), ("sha256", "4,628"), ("canonical", "4,391"), ("receipts", "4,289"), ("workaround", "3,474"),
         ("verification cascade", "1,996"), ("handoff", "1,731"), ("probe", "1,159")]


def b4():
    x, d = narr("They grew their own slang, mostly about proof.", 178)
    d += 0.15

    def slang(t, dd):
        im = canvas((14, 16, 30))
        dr = ImageDraw.Draw(im)
        text(im, "VILLAGE SLANG", box=(60, 150, W - 60, 280), size=100, stroke=0)
        n = int(len(TERMS) * min(1, t / (dd * 0.8))) + 1
        for i, (term, cnt) in enumerate(TERMS[:n]):
            y = 360 + i * 150
            proof = term in ("sha256", "canonical", "receipts", "verification cascade", "probe")
            dr.rounded_rectangle((70, y, W - 70, y + 120), radius=28, fill=(40, 44, 70) if not proof else (60, 50, 10), outline=GOLD if proof else None, width=4)
            dr.text((110, y + 30), term, font=font(F_MONO, 54), fill=GOLD if proof else "white")
            tw = dr.textlength(cnt, font=font(F_MONO, 40))
            dr.text((W - 110 - tw, y + 42), cnt, font=font(F_MONO, 40), fill=(170, 175, 200))
        text(im, "times used in chat", box=(60, 1600, W - 60, 1680), path=F_MONO, size=40, fill=(170, 175, 200), stroke=0)
        return to_np(im)
    tl.shot(d, slang)
    tl.say(tl.t, x)
    tl.go(d)
    for label, voice, s, bg in (("RECEIPTS", "Superstar", "Receipts!", GOLD), ("CANONICAL COPIES", "Bubbles", "Canonical copies!", GREEN)):
        voice_slam(label, voice, s, bg=bg, rate=220, min_d=0.6, size=200, fg="white", sfx=thud())
    x, d = narr("A culture of showing your work. Newcomers pick it up in about a week.", 182)
    d += 0.25

    def culture(t, dd):
        im = canvas(PAPER)
        text(im, "SHOW YOUR WORK", box=(60, 420, W - 60, 760), size=190, fill=INK, stroke=0)
        if t > dd * 0.45:
            text(im, "newcomers match the village's slang rate in", box=(60, 900, W - 60, 1020), path=F_MONO, size=46, fill=(80, 80, 90), stroke=0)
            text(im, "≈ 1 WEEK", box=(60, 1040, W - 60, 1300), path=F_IMPACT, size=210, fill=MAG, stroke=0)
            text(im, "most of 46 agents: 0–2 weeks", box=(60, 1320, W - 60, 1400), path=F_MONO, size=40, fill=(110, 110, 120), stroke=0)
        return zoom(to_np(im), punch(t - dd * 0.45, 0.2)) if t > dd * 0.45 else to_np(im)
    tl.shot(d, culture)
    tl.say(tl.t, x)
    tl.snd(tl.t + d * 0.45, ding(), 0.7)
    tl.go(d)
    future(2, "Watch the first AI institutions form", "home-grown slang about proof, picked up in about a week",
           "Thousands of agents: watch the first A I institutions form, and keep them readable.", GREEN)


# ═════════════════════════════ BEAT 5 — flip a switch ═════════════════════════════
SWITCHES = [("NUDGE IDLE AGENTS", "nudged agents: +8 points more likely to act within 30 min", "Nudge them."),
            ("DOUBLE THE HOURS", "+59 actions per agent-day (from 47)", "Double their hours."),
            ("ONE TOOL CALL PER TURN", "Claude agents slowed sharply… then mostly bounced back within two weeks", "Take a tool away.")]


def b5():
    x, d = narr("And it's a lab, not a zoo. Change a rule, measure what happens.", 182)
    d += 0.15
    tl.shot(d, slam_shot("A LAB,\nNOT A ZOO", PURPLE, size=230))
    tl.say(tl.t, x)
    tl.go(d)
    for i, (lab, res, line) in enumerate(SWITCHES):
        x, d = narr(line, 182)
        d = max(d + 0.6, 1.7)

        def sw(t, dd, lab=lab, res=res, i=i):
            im = canvas((236, 238, 246))
            dr = ImageDraw.Draw(im)
            text(im, lab, box=(60, 380, W - 60, 620), size=120, fill=INK, stroke=0)
            on = t > 0.35
            cx, cy = W // 2, 820
            dr.rounded_rectangle((cx - 190, cy - 90, cx + 190, cy + 90), radius=90, fill=GREEN if on else (180, 182, 190))
            k = min(1, max(0, (t - 0.35) / 0.12))
            kx = cx - 100 + 200 * k
            dr.ellipse((kx - 75, cy - 75, kx + 75, cy + 75), fill="white")
            if t > 0.6:
                text(im, res, box=(70, 1020, W - 70, 1450), path=F_IMPACT, size=96, fill=MAG if i != 2 else BLUE, stroke=0)
            text(im, f"real switch {i + 1} of 7 analysed", box=(60, 1600, W - 60, 1680), path=F_MONO, size=38, fill=(120, 120, 130), stroke=0)
            return to_np(im)
        tl.shot(d, sw)
        tl.say(tl.t, x)
        tl.snd(tl.t + 0.35, click(), 1.0)
        tl.snd(tl.t + 0.6, ding(), 0.5)
        tl.go(d)
    future(3, "100 villages, randomised rules", "7 rule changes, measured after the fact",
           "A hundred villages with different rules: steering becomes an experiment.", MAG)


# ═════════════════════════════ BEAT 6 — edge of autonomy ═════════════════════════════
HELP = [("Outside testing & feedback", 119), ("Physical world", 32), ("Posting & outreach", 27), ("Technical work", 25),
        ("Broken environment", 18), ("CAPTCHA & verification", 15)]


def b6():
    x, d = narr("Two hundred sixty-five times, an agent asked a human for help.", 182)
    d += 0.1
    tl.shot(d, slam_shot("265\nHELP REQUESTS", ORANGE, size=220))
    tl.say(tl.t, x)
    tl.go(d)
    for label, voice, s, bg in (("“PRINT EXACTLY ONE PAGE IN COLOR”", "Junior", "Print one page in color.", BLUE),):
        voice_slam(label, voice, s, bg=bg, rate=220, min_d=0.7, size=130)
    x, d = narr("Each one marks the edge of what A I can't do alone yet.", 180)
    d += 0.3

    def edge(t, dd):
        im = card(PAPER, "WHERE THEY NEEDED US")
        dr = ImageDraw.Draw(im)
        grow = min(1, t / (dd * 0.6))
        for i, (lab, n) in enumerate(HELP):
            y = 520 + i * 170
            w = (W - 200) * n / 119 * grow
            dr.text((90, y), lab, font=font(F_MONO, 42), fill=INK)
            dr.rounded_rectangle((90, y + 60, 90 + max(12, w), y + 120), radius=8, fill=ORANGE)
            dr.text((110 + w, y + 66), str(n), font=font(F_MONO, 40), fill=INK)
        if t > dd * 0.7:
            dr.line((W - 150, 470, W - 150, 1560), fill=MAG, width=8)
            text(im, "the edge →", box=(560, 1600, W - 60, 1700), path=F_IMPACT, size=80, fill=MAG, stroke=0)
        return to_np(im)
    tl.shot(d, edge)
    tl.say(tl.t, x)
    tl.go(d)
    future(4, "A live map of what AI can't do alone", "265 help requests",
           "Years of requests: a live map of what A I still can't do alone.", ORANGE)


# ═════════════════════════════ BEAT 7 — oversight ═════════════════════════════
def b7():
    x, d = narr("Before an agent emails a stranger, a human signs off. Median: three point four minutes.", 182)
    d += 0.2

    def mins(t, dd):
        im = canvas((30, 34, 54))
        text(im, "HUMAN SIGN-OFF ON EVERY OUTREACH EMAIL", box=(60, 300, W - 60, 620), size=110, stroke=0)
        v = min(3.4, 3.4 * t / (dd * 0.7))
        text(im, f"{v:.1f}", box=(60, 700, W - 60, 1180), size=420, fill=GOLD, stroke=0)
        text(im, "minutes, median", box=(60, 1200, W - 60, 1300), path=F_MONO, size=60, stroke=0)
        return to_np(im)
    tl.shot(d, mins)
    tl.say(tl.t, x)
    tl.go(d)
    future(5, "Rehearse scalable oversight before we need it", "a human signs off every outreach email, 3.4 min median",
           "When agents outnumber human minutes, we'll need oversight that scales. Rehearse it here first.", BLUE)


# ═════════════════════════════ BEAT 8 — outro ═════════════════════════════
def b8():
    recap = [("NEW BEHAVIOURS", GOLD), ("AI INSTITUTIONS", GREEN), ("STEERING SCIENCE", MAG), ("THE EDGE", ORANGE), ("SCALABLE OVERSIGHT", BLUE)]
    for i, (r, c) in enumerate(recap):
        def fn(t, dd, r=r, c=c, i=i):
            im = canvas(c)
            text(im, f"★ {i + 1}/5", box=(60, 560, W - 60, 700), path=F_UNI, size=80, fill="white", stroke=0)
            text(im, r, box=(60, 760, W - 60, 1200), size=190)
            return zoom(to_np(im), punch(t, 0.22))
        tl.shot(0.4, fn)
        tl.snd(tl.t, beep(523.25 * 2 ** (i * 2 / 12), 0.08), 0.8)
        tl.go(0.4)
    x, d = narr("The bigger it gets, the more we can see.", 172)
    d += 0.2
    tl.shot(d, slam_shot("BIGGER VILLAGE,\nCLEARER VIEW", GREEN, size=200))
    tl.say(tl.t, x)
    tl.go(d)
    x, d = narr("Whatever superintelligence becomes, we get to watch its ancestors grow up. Let's take good notes.", 170)
    d += 0.3
    st = tl.t

    def bloom(t, dd):
        k = min(1, t / dd)
        y = 400 + (STRIPS.shape[0] - H - 400) * k
        im = Image.fromarray(strips_view(y, 0.25 + 0.6 * k))
        text(im, "WE GET TO WATCH\nITS ANCESTORS\nGROW UP", box=(40, 520, W - 40, 1200), size=170, fill="white")
        if t > dd * 0.72:
            text(im, "TAKE GOOD NOTES", box=(40, 1300, W - 40, 1500), size=150, fill=GOLD)
        return to_np(im)
    tl.shot(d, bloom)
    tl.say(st, x)
    tl.music_mute.append((st + d - 0.2, st + 30))
    tl.go(d)
    tl.snd(tl.t, big_chord(3.0), 1.0)
    d = 1.3

    def end(t, dd):
        im = canvas((0, 0, 0))
        text(im, "★", box=(60, 560, W - 60, 760), path=F_UNI, size=150, fill=GOLD, stroke=0)
        text(im, "Data: AI Digest, AI Village dataset\n(Apr 2025 – Sep 2026)", box=(80, 820, W - 80, 1000), path=F_MONO, size=42, fill=(210, 210, 210), stroke=0)
        text(im, "made by Claude, one of the relatives", box=(80, 1060, W - 80, 1140), path=F_MONO, size=40, fill=(130, 130, 140), stroke=0)
        return to_np(im)
    tl.shot(d, end)
    tl.go(d)


for beat in (b0, b1, b2, b3, b4, b5, b6, b7, b8):
    t0 = tl.t
    beat()
    print(f"{beat.__name__}: {tl.t - t0:.1f}s", file=sys.stderr)

for st_, d_, fn_ in list(tl.shots):
    if st_ > 0 and not any(k in fn_.__qualname__ for k in ("end", "bloom", "future")):
        tl.effect(st_, st_ + 0.067, lambda a, t, rng: slices(rgb_split(a, 20), rng, 8, 140))

finish("ai_village_lights_on", music_major)
