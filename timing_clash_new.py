#!/usr/bin/env python3
"""
TIMING CLASH  -  a self-contained pixel-arcade timing game.

Everything the game needs lives in THIS single .py file:
  * All graphics are generated procedurally as crisp pixel art (no image files)
  * All sound effects are synthesized on the fly (no audio files)
  * Save data is optional and stored next to this script

HOW TO PLAY
  A laser cursor sweeps up and down the tower. Slam your key at exactly
  the right moment to land inside the glowing TARGET zone. Perfect center
  hits score DOUBLE. Chain hits for a streak multiplier, charge your
  COMBO meter and unleash FEVER MODE for massive points!

MODES
  [1] Career      - 25 hand-balanced procedural levels, stars & high scores
  [2] Tug-of-War  - local 2-player battle (P1 = A, P2 = L), best-of-3 option

Run:  python timing_clash.py     (requires: pip install pygame)
"""

import json
import math
import os
import random
import sys
import tempfile

try:
    import pygame
except ImportError:  # pragma: no cover
    print("This game needs pygame.  Install it with:  pip install pygame")
    sys.exit(1)

# ======================================================================
# DISPLAY / CORE CONSTANTS
# ======================================================================
WIDTH, HEIGHT = 1000, 600
FPS = 60

# Internal low-res buffer -> chunky pixels when scaled up 2x
PX_W, PX_H = WIDTH // 2, HEIGHT // 2
PIXEL_SCALE = 2

# Retro palette
C_BG_TOP      = (18, 14, 46)
C_BG_BOT      = (44, 22, 74)
C_HORIZON     = (96, 48, 140)
C_STAR        = (220, 220, 255)
C_P1          = (90, 200, 255)
C_P1_DARK     = (30, 90, 160)
C_P2          = (255, 110, 90)
C_P2_DARK     = (160, 40, 40)
C_GREEN       = (90, 240, 120)
C_GOLD        = (255, 210, 80)
C_WHITE       = (240, 240, 245)
C_DIM         = (140, 140, 170)
C_VERY_DIM    = (55, 55, 80)
C_RED         = (255, 80, 80)
C_FEVER_A     = (255, 90, 160)
C_FEVER_B     = (255, 170, 60)

BAR_W, BAR_H = 25, 200          # in PIXEL units (doubled on screen)
BAR_Y = 60                      # top of bars, pixel units

SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "timing_clash_save.json")

# ======================================================================
# PYGAME INIT + FONTS (built-in font, zero external files)
# ======================================================================
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
buffer = pygame.Surface((PX_W, PX_H))          # low-res pixel canvas
pygame.display.set_caption("Timing Clash")
clock = pygame.time.Clock()

font_giant  = pygame.font.Font(None, 150)
font_large  = pygame.font.Font(None, 60)
font_medium = pygame.font.Font(None, 30)
font_small  = pygame.font.Font(None, 22)
font_tiny   = pygame.font.Font(None, 16)


def draw_text(surf, text, font, color, x, y, center=True):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surf.blit(img, rect)


def draw_text_shadow(surf, text, font, color, x, y, center=True,
                     shadow=(0, 0, 0)):
    draw_text(surf, text, font, shadow, x + 2, y + 2, center)
    draw_text(surf, text, font, color, x, y, center)


# ======================================================================
# SAVE SYSTEM (atomic, never crashes)
# ======================================================================
def load_save():
    try:
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
        return {
            "highest_unlocked_level": max(1, int(data.get("highest_unlocked_level", 1))),
            "stars": int(data.get("stars", 0)),
            "highscores": dict(data.get("highscores", {})),
            "level_stars": dict(data.get("level_stars", {})),
        }
    except Exception:
        return {"highest_unlocked_level": 1, "stars": 0,
                "highscores": {}, "level_stars": {}}


def write_save(data):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SAVE_FILE) or ".",
                                   suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, SAVE_FILE)
    except Exception:
        pass


# ======================================================================
# SETTINGS (defined before SoundEngine so sound.play() can consult them)
# ======================================================================
SETTINGS = {
    "screen_shake": True,
    "particles": True,
    "show_fps": False,
    "hardcore_penalties": False,
    "sound": True,
}
SETTING_KEYS = list(SETTINGS.keys())
SETTING_LABELS = {
    "screen_shake": "Screen Shake FX",
    "particles": "Particle Effects",
    "show_fps": "FPS Counter",
    "hardcore_penalties": "Hardcore Penalties (2s Freeze)",
    "sound": "Sound Effects",
}

# ======================================================================
# SOUND ENGINE - tiny synth, all waveforms generated in memory
# ======================================================================
class SoundEngine:
    def __init__(self):
        self.enabled = False
        self.mixer_ok = False
        try:
            pygame.mixer.pre_init(22050, -16, 1, 256)
            pygame.mixer.init(22050, -16, 1, 256)
            self.mixer_ok = True
        except Exception:
            self.mixer_ok = False
        self.sounds = {}
        if self.mixer_ok:
            self._build()

    @staticmethod
    def _to_sound(samples):
        buf = bytearray(2 * len(samples))
        for i, s in enumerate(samples):
            v = int(max(-1.0, min(1.0, s)) * 30000)
            buf[2 * i] = v & 0xFF
            buf[2 * i + 1] = (v >> 8) & 0xFF
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _tone(self, freq, dur, vol=0.5, decay=6.0, slide=0.0, wave="sine"):
        rate = 22050
        n = int(rate * dur)
        out = []
        phase = 0.0
        for i in range(n):
            f = freq + slide * (i / n)
            phase += f / rate
            t = phase * 2 * math.pi
            if wave == "sine":
                s = math.sin(t)
            elif wave == "square":
                s = 1.0 if math.sin(t) >= 0 else -1.0
            elif wave == "triangle":
                s = 2 * abs(2 * (phase % 1) - 1) - 1
            else:  # noise
                s = random.uniform(-1, 1)
            env = math.exp(-decay * (i / n)) * (1 if i > rate * 0.002 else i / (rate * 0.002))
            out.append(s * env * vol)
        return self._to_sound(out)

    def _chord(self, freqs, dur, vol=0.35, decay=4.0, wave="square"):
        rate = 22050
        n = int(rate * dur)
        out = []
        for i in range(n):
            s = sum(math.sin(2 * math.pi * f * i / rate) for f in freqs) / len(freqs)
            env = math.exp(-decay * (i / n))
            if wave == "square":
                s = 1.0 if s >= 0 else -1.0
            out.append(s * env * vol)
        return self._to_sound(out)

    def _noise(self, dur, vol=0.4, decay=8.0):
        rate = 22050
        n = int(rate * dur)
        out = [random.uniform(-1, 1) * math.exp(-decay * (i / n)) * vol for i in range(n)]
        return self._to_sound(out)

    def _build(self):
        try:
            self.sounds["hit"] = self._tone(660, 0.09, 0.45, 9, 220, "square")
            self.sounds["perfect"] = self._chord([880, 1320], 0.16, 0.4, 5)
            self.sounds["miss"] = self._tone(180, 0.22, 0.5, 7, -80, "square")
            self.sounds["fever"] = self._chord([523, 659, 784, 1046], 0.4, 0.4, 3)
            self.sounds["select"] = self._tone(520, 0.06, 0.35, 12, 120, "square")
            self.sounds["back"] = self._tone(300, 0.08, 0.35, 12, -60, "square")
            self.sounds["win"] = self._chord([523, 659, 784], 0.55, 0.4, 2.5)
            self.sounds["lose"] = self._tone(300, 0.5, 0.4, 4, -180, "triangle")
            self.sounds["coin"] = self._chord([988, 1319], 0.12, 0.3, 8)
            self.sounds["crash"] = self._noise(0.3, 0.5, 7)
            self.enabled = True
        except Exception:
            self.enabled = False

    def play(self, name):
        if self.enabled and SETTINGS.get("sound", True) and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass


sound = SoundEngine()

# ======================================================================
# PIXEL ART SPRITES - defined as ASCII grids, rendered once at startup
# ======================================================================
def render_sprite(rows, palette, scale=1):
    h = len(rows)
    w = max(len(r) for r in rows)
    surf = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            col = palette.get(ch)
            if col is not None:
                pygame.draw.rect(surf, col,
                                 (x * scale, y * scale, scale, scale))
    return surf


PAL_ROCKET = {
    ".": None,
    "R": (235, 235, 245),   # hull
    "r": (170, 175, 200),   # hull shade
    "O": (255, 90, 90),     # nose / fins
    "o": (190, 50, 50),      # fin shade
    "C": (120, 220, 255),    # cockpit glass
    "c": (60, 140, 210),     # glass shade
    "F": (255, 200, 60),     # flame outer
    "f": (255, 110, 40),     # flame inner
}

ROCKET_ROWS = [
    "....OOO....",
    "...ORRO...",
    "..ORRRRO..",
    ".oRRCCRRo.",
    ".oRcCCcRo.",
    ".oRRRRRRo.",
    "oRRRrrRRRo",
    "ORRrrrrRRO",
    "ORrrrrrrRO",
    ".orrrrrro.",
    "..oFOFOf..",
    "...Ffff...",
    "....ff....",
]

ROCKET_FLAME_ROWS = [
    "....OOO....",
    "...ORRO...",
    "..ORRRRO..",
    ".oRRCCRRo.",
    ".oRcCCcRo.",
    ".oRRRRRRo.",
    "oRRRrrRRRo",
    "ORRrrrrRRO",
    "ORrrrrrrRO",
    ".orrrrrro.",
    "..oFOFOFo.",
    ".oFFFFFFo.",
    "..fFFFFf..",
    "...ffff...",
    "....ff....",
]

rocket_idle = render_sprite(ROCKET_ROWS, PAL_ROCKET)
rocket_flame = render_sprite(ROCKET_FLAME_ROWS, PAL_ROCKET)


def recolor_rocket(rows, color):
    pal = dict(PAL_ROCKET)
    pal["O"] = color
    pal["o"] = tuple(max(0, c - 70) for c in color)
    return render_sprite(rows, pal)


rocket_p2_idle = recolor_rocket(ROCKET_ROWS, C_P2)
rocket_p2_flame = recolor_rocket(ROCKET_FLAME_ROWS, C_P2)

PAL_HEART = {
    ".": None,
    "R": (255, 70, 90),
    "r": (200, 40, 70),
    "W": (255, 190, 200),
}
HEART_ROWS = [
    ".RR..RR.",
    "RWRRRWWR",   # W highlight
    "RRRRRRRR",
    "RRRRRRRR",
    ".rRRRRr.",
    "..rRRr..",
    "...rr...",
    "........",
]
heart_full = render_sprite(HEART_ROWS, PAL_HEART)
PAL_HEART_OFF = {"R": (70, 60, 85), "r": (50, 45, 65), "W": (90, 85, 105)}
heart_empty = render_sprite(HEART_ROWS, PAL_HEART_OFF)

PAL_SKULL = {
    ".": None,
    "W": (225, 225, 235),
    "K": (30, 30, 40),
    "G": (120, 120, 135),
}
SKULL_ROWS = [
    ".WWWWW.",
    "WWWWWWW",
    "WKWWWKW",
    "WKWWWKW",
    "WWWWWWW",
    "W.WWW.W",
    ".WWWWW.",
    ".W.W.W.",
]
skull_icon = render_sprite(SKULL_ROWS, PAL_SKULL)

PAL_STAR = {
    ".": None,
    "Y": (255, 210, 80),
    "y": (210, 150, 40),
    "W": (255, 245, 200),
}
STAR_ROWS = [
    "....Y....",
    "....Y....",
    "...YWY...",
    "YYYYYYYYY",
    ".YYYYYYY.",
    "..YYYYY..",
    ".YYY.YYY.",
    ".YY...YY.",
]
star_on = render_sprite(STAR_ROWS, PAL_STAR)
star_off = render_sprite(STAR_ROWS, {"Y": (60, 60, 80), "y": (45, 45, 60),
                                     "W": (75, 75, 95)})

PAL_TROPHY = {
    ".": None,
    "Y": (255, 205, 70),
    "y": (200, 145, 40),
    "W": (255, 245, 190),
    "B": (120, 80, 40),
}
TROPHY_ROWS = [
    "YYYYYYYYY",
    "YWYYYYYy.",
    " YYYYYYY.",
    ".YYYYYYY.",
    "..YYYYY..",
    "...YYY...",
    "....Y....",
    "...BBB...",
    "..BBBBB..",
]
trophy_icon = render_sprite(TROPHY_ROWS, PAL_TROPHY)

PAL_ZAP = {
    ".": None,
    "Y": (255, 235, 90),
    "O": (255, 170, 40),
}
ZAP_ROWS = [
    "...YY..",
    "..YYY..",
    ".YYYYY.",
    "YYYYYO.",
    "..YYY..",
    ".YYY...",
    "YYY....",
    "YY.....",
]
zap_icon = render_sprite(ZAP_ROWS, PAL_ZAP)

PAL_KEYCAP = {
    ".": None,
    "L": (205, 205, 220),
    "D": (120, 120, 140),
    "K": (40, 40, 55),
}
KEYCAP_ROWS = [
    "LLLLLLL",
    "LDDDDDL",
    "LDKKKDL",
    "LDKKKDL",
    "LDKKKDL",
    "LDDDDDL",
    "LLLLLLL",
]
keycap_blue = render_sprite(KEYCAP_ROWS,
                            {**PAL_KEYCAP, "L": C_P1, "D": C_P1_DARK})
keycap_red = render_sprite(KEYCAP_ROWS,
                           {**PAL_KEYCAP, "L": C_P2, "D": C_P2_DARK})

# ======================================================================
# BACKGROUND - starfield + parallax skyline (drawn onto low-res buffer)
# ======================================================================
rng_bg = random.Random(1337)
STARS = [(rng_bg.randint(0, PX_W - 1), rng_bg.randint(0, PX_H // 2),
          rng_bg.choice([(180, 180, 220), C_STAR, (255, 240, 180)]),
          rng_bg.random() * 6.28) for _ in range(70)]

def make_skyline(seed, base_y, hmin, hmax, color):
    r = random.Random(seed)
    buildings = []
    x = 0
    while x < PX_W:
        w = r.randint(14, 34)
        h = r.randint(hmin, hmax)
        wins = []
        for wy in range(base_y - h + 4, base_y - 3, 6):
            for wx in range(x + 3, x + w - 3, 5):
                if r.random() < 0.4:
                    wins.append((wx, wy, r.choice([(255, 220, 120),
                                                   (120, 220, 255),
                                                   (255, 150, 180)])))
        buildings.append((x, base_y - h, w, h, wins))
        x += w + r.randint(2, 6)
    return buildings, color

SKY_FAR = make_skyline(42, PX_H - 40, 30, 90, (38, 30, 70))
SKY_NEAR = make_skyline(7, PX_H - 8, 45, 130, (24, 18, 48))


def draw_background(surf, t, fever=False):
    # vertical gradient sky
    for y in range(PX_H):
        f = y / PX_H
        if fever:
            pulse = 0.5 + 0.5 * math.sin(t * 6)
            col = (int(40 + 60 * pulse + 30 * f),
                   int(12 + 25 * f),
                   int(40 + 20 * (1 - f)))
        else:
            col = (int(C_BG_TOP[0] + (C_BG_BOT[0] - C_BG_TOP[0]) * f),
                   int(C_BG_TOP[1] + (C_BG_BOT[1] - C_BG_TOP[1]) * f),
                   int(C_BG_TOP[2] + (C_BG_BOT[2] - C_BG_TOP[2]) * f))
        pygame.draw.line(surf, col, (0, y), (PX_W, y))

    # twinkling stars
    for sx, sy, sc, ph in STARS:
        b = 0.55 + 0.45 * math.sin(t * 2.4 + ph)
        c = tuple(int(v * b) for v in sc)
        surf.set_at((sx, sy), c)

    # moon
    pygame.draw.circle(surf, (235, 235, 215), (PX_W - 70, 46), 14)
    pygame.draw.circle(surf, (210, 210, 195), (PX_W - 74, 43), 4)
    pygame.draw.circle(surf, (210, 210, 195), (PX_W - 64, 51), 3)

    # skylines
    buildings, colr = SKY_FAR
    for bx, by, bw, bh, wins in buildings:
        pygame.draw.rect(surf, colr, (bx, by, bw, bh))
        for wx, wy, wc in wins:
            if 0 <= wx < PX_W and wy < PX_H:
                surf.set_at((wx, wy), wc)
                surf.set_at((wx + 1, wy), wc)
    buildings, colr = SKY_NEAR
    for bx, by, bw, bh, wins in buildings:
        pygame.draw.rect(surf, colr, (bx, by, bw, bh))
        for wx, wy, wc in wins:
            blink = ((int(t * 2) + wx + bx) % 7) != 0
            if blink and 0 <= wx < PX_W:
                surf.set_at((wx, wy), wc)

    # ground strip
    pygame.draw.rect(surf, (14, 10, 30), (0, PX_H - 8, PX_W, 8))


# ======================================================================
# PARTICLES
# ======================================================================
class Particle:
    def __init__(self, x, y, color, vx=None, vy=None, life=None, size=None,
                 gravity=300):
        self.x, self.y = x, y
        self.vx = random.uniform(-140, 140) if vx is None else vx
        self.vy = random.uniform(-170, 40) if vy is None else vy
        self.life = self.max_life = life or random.uniform(0.3, 0.7)
        self.color = color
        self.size = size or random.choice([1, 1, 2, 2, 3])
        self.gravity = gravity

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        self.life -= dt

    def draw(self, surf):
        a = max(0.0, self.life / self.max_life)
        s = max(1, int(self.size * (0.5 + a * 0.5)))
        pygame.draw.rect(surf, self.color, (int(self.x), int(self.y), s, s))


def spawn_burst(particles, x, y, colors, n=24, spread=160):
    for _ in range(n):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(40, spread)
        particles.append(Particle(x, y, random.choice(colors),
                                  vx=math.cos(ang) * spd,
                                  vy=math.sin(ang) * spd - 60))


# ======================================================================
# FLOATING SCORE POPUPS
# ======================================================================
class Popup:
    def __init__(self, text, x, y, color, big=False):
        self.text, self.x, self.y = text, x, y
        self.color = color
        self.life = self.max_life = 0.9
        self.big = big

    def update(self, dt):
        self.y -= 34 * dt
        self.life -= dt

    def draw(self, surf):
        a = max(0.0, self.life / self.max_life)
        col = tuple(int(c * (0.4 + 0.6 * a)) for c in self.color)
        font = font_medium if self.big else font_small
        draw_text_shadow(surf, self.text, font, col, int(self.x), int(self.y))


# ======================================================================
# PLAYER BAR (the timing tower + rocket cursor)
# ======================================================================
class PlayerBar:
    def __init__(self, px_x, color, dark_color, prefix, rocket_idle_img,
                 rocket_flame_img, cursor_speed=170, target_height=40):
        self.rect = pygame.Rect(px_x * PIXEL_SCALE // PIXEL_SCALE, 0, 0, 0)
        self.px = px_x                       # left edge, pixel units
        self.color = color
        self.dark = dark_color
        self.prefix = prefix
        self.img_idle = rocket_idle_img
        self.img_flame = rocket_flame_img

        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.lives = 3
        self.fever = 0.0                     # 0..1 combo meter
        self.fever_time = 0.0                # seconds of active fever
        self.hits = 0
        self.perfects = 0

        self.cursor_y = float(BAR_Y)
        self.cursor_speed = cursor_speed
        self.base_speed = cursor_speed
        self.cursor_dir = 1

        self.target_h = target_height
        self.target_y = BAR_Y + 20
        self.randomize_target()

        self.penalty_timer = 0.0
        self.flash_timer = 0.0               # white hit-flash on target
        self.red_flash = 0.0                 # miss flash
        self.wobble = 0.0
        self.last_result = None              # ("PERFECT"/"HIT"/"MISS", t)

    def randomize_target(self):
        self.target_y = random.randint(BAR_Y, BAR_Y + BAR_H - self.target_h)

    @property
    def fever_active(self):
        return self.fever_time > 0

    def update(self, dt):
        if self.penalty_timer > 0:
            self.penalty_timer -= dt
        if self.flash_timer > 0:
            self.flash_timer -= dt
        if self.red_flash > 0:
            self.red_flash -= dt
        if self.wobble > 0:
            self.wobble -= dt * 4
        if self.fever_time > 0:
            self.fever_time -= dt
            if self.fever_time <= 0:
                self.fever = 0.0

        if self.penalty_timer > 0:
            return

        speed_mult = 1.35 if self.fever_active else 1.0
        self.cursor_y += self.cursor_speed * speed_mult * self.cursor_dir * dt
        top, bot = BAR_Y, BAR_Y + BAR_H
        if self.cursor_y <= top:
            self.cursor_y = top
            self.cursor_dir = 1
        elif self.cursor_y >= bot:
            self.cursor_y = bot
            self.cursor_dir = -1

    def attempt_score(self):
        """Returns 'PERFECT', 'GOOD' or 'MISS'."""
        if self.penalty_timer > 0:
            return None
        cy = self.cursor_y
        t0, t1 = self.target_y, self.target_y + self.target_h
        mid = (t0 + t1) / 2
        perfect_band = max(4.0, self.target_h * 0.18)

        if t0 <= cy <= t1:
            perfect = abs(cy - mid) <= perfect_band
            mult = 1 + self.streak // 3
            if self.fever_active:
                mult *= 2
            pts = (2 if perfect else 1) * mult
            self.score += pts
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.hits += 1
            if perfect:
                self.perfects += 1
            gain = 0.14 if perfect else 0.09
            if not self.fever_active:
                self.fever = min(1.0, self.fever + gain)
                if self.fever >= 1.0:
                    self.fever_time = 5.0
            self.flash_timer = 0.25
            self.cursor_speed = min(self.base_speed + 130,
                                   self.cursor_speed + 6)
            self.randomize_target()
            self.last_result = ("PERFECT" if perfect else "GOOD", 0.7)
            return "PERFECT" if perfect else "GOOD"
        else:
            self.streak = 0
            self.lives -= 1
            self.penalty_timer = 1.0
            self.red_flash = 0.4
            self.wobble = 1.0
            if not self.fever_active:
                self.fever = max(0.0, self.fever - 0.25)
            self.cursor_speed = max(self.base_speed, self.cursor_speed - 12)
            self.last_result = ("MISS", 0.7)
            return "MISS"

    # ---------------- drawing (pixel coords on low-res buffer) ----------
    def draw(self, surf, particles, popups, t):
        x, y = self.px, BAR_Y
        wob = int(round(math.sin(t * 40) * self.wobble * 2)) if self.wobble > 0 else 0
        x += wob

        # tower body
        pygame.draw.rect(surf, (26, 22, 48), (x, y, BAR_W, BAR_H))
        # side rails with rivets
        for rail_x in (x, x + BAR_W - 2):
            pygame.draw.rect(surf, self.dark, (rail_x, y, 2, BAR_H))
            for ry in range(y + 3, y + BAR_H - 2, 9):
                surf.set_at((rail_x + 1, ry), (255, 255, 255))
        # top/bottom caps
        pygame.draw.rect(surf, self.dark, (x - 2, y - 4, BAR_W + 4, 4))
        pygame.draw.rect(surf, self.dark, (x - 2, y + BAR_H, BAR_W + 4, 4))
        # tick marks
        for ty in range(y + 10, y + BAR_H, 20):
            pygame.draw.line(surf, (48, 44, 80), (x + 4, ty), (x + 8, ty))

        # target zone
        ty0 = self.target_y
        th = self.target_h
        glow = 0.6 + 0.4 * math.sin(t * 5)
        base_col = C_FEVER_B if self.fever_active else C_GREEN
        zone_col = tuple(int(c * (0.55 + 0.45 * glow)) for c in base_col)
        pygame.draw.rect(surf, (*zone_col,), (x + 2, ty0, BAR_W - 4, th))
        # perfect band (brighter core)
        pb = max(2, int(th * 0.18))
        pmid = ty0 + th // 2
        pygame.draw.rect(surf, C_WHITE, (x + 2, pmid - pb // 2, BAR_W - 4, pb))
        # pulsing outline
        oc = tuple(min(255, int(c * (0.7 + 0.3 * glow))) for c in base_col)
        pygame.draw.rect(surf, oc, (x + 1, ty0 - 1, BAR_W - 2, th + 2), 1)
        if self.flash_timer > 0:
            fs = pygame.Surface((BAR_W, th + 8), pygame.SRCALPHA)
            fs.fill((255, 255, 255, int(160 * self.flash_timer / 0.25)))
            surf.blit(fs, (x, ty0 - 4))

        # rocket cursor
        rcx = x + BAR_W // 2
        rcy = int(self.cursor_y)
        img = self.img_flame if (self.penalty_timer <= 0 and
                                 int(t * 12) % 2 == 0) else self.img_idle
        if self.penalty_timer > 0:
            img = self.img_idle
        iw, ih = img.get_size()
        surf.blit(img, (rcx - iw // 2, rcy - ih // 2))
        if self.penalty_timer > 0 and int(t * 8) % 2 == 0:
            ov = pygame.Surface((iw, ih), pygame.SRCALPHA)
            ov.fill((255, 60, 60, 140))
            surf.blit(ov, (rcx - iw // 2, rcy - ih // 2),
                      special_flags=pygame.BLEND_ALPHA_SDL2)

        # red miss flash over whole bar
        if self.red_flash > 0:
            ov = pygame.Surface((BAR_W + 4, BAR_H + 8), pygame.SRCALPHA)
            ov.fill((255, 40, 40, int(110 * self.red_flash / 0.4)))
            surf.blit(ov, (x - 2, y - 4))

        # last-result label under the bar
        if self.last_result:
            label, ltime = self.last_result
            if ltime > 0:
                col = {"PERFECT": C_GOLD, "GOOD": C_GREEN, "MISS": C_RED}[label]
                fnt = font_small if label == "PERFECT" else font_tiny
                draw_text_shadow(surf, label, fnt, col,
                                 x + BAR_W // 2, y + BAR_H + 14)

    def update_timers(self, dt):
        if self.last_result and self.last_result[1] > 0:
            self.last_result = (self.last_result[0], self.last_result[1] - dt)


# ======================================================================
# LEVEL GENERATION
# ======================================================================
LEVEL_COUNT = 25
DESCRIPTORS = ["Ignition", "Liftoff", "Focus", "Drift", "Rhythm", "Tempo",
               "Surge", "Precision", "Velocity", "Momentum", "Gauntlet",
               "Storm", "Blitz", "Nebula", "Quasar", "Overdrive", "Apex",
               "Zenith", "Inferno", "Singularity", "Hyperlight", "Eclipse",
               "Nova Burst", "Final Frontier", "The Core"]


def generate_career_level(level_num):
    target_score = 6 + min(level_num * 3, 60)
    base_speed = min(300, 110 + (level_num - 1) * 9)      # pixel-units/sec
    target_height = max(14, 44 - (level_num - 1) * 1)
    time_limit = max(12.0, target_score * 1.15 + 6.0)
    title = f"LVL {level_num}: {DESCRIPTORS[min(level_num - 1, len(DESCRIPTORS) - 1)]}"
    return {
        "level": level_num,
        "title": title,
        "target_score": target_score,
        "time_limit": time_limit,
        "cursor_speed": base_speed,
        "target_height": target_height,
    }


def stars_for(score_data, p1):
    """0-3 stars based on performance."""
    stars = 0
    if p1.score >= score_data["target_score"]:
        stars = 1
        ratio = p1.score / max(1, score_data["target_score"])
        if ratio >= 1.5 or p1.lives >= 2:
            stars = 2
        if ratio >= 1.8 and p1.lives == 3 and p1.perfects >= 3:
            stars = 3
    return stars


# ======================================================================
# MENU HELPERS - pixel-art menu cards with animated icons
# ======================================================================
MENU_ITEMS = [
    ("1", "CAREER MISSIONS", C_GOLD, zap_icon),
    ("2", "TUG OF WAR  (2P)", C_P2, trophy_icon),
    ("3", "HOW TO PLAY", C_P1, rocket_idle),
    ("4", "SETTINGS", C_DIM, skull_icon),
]


def draw_menu_card(surf, cx, cy, w, h, hot, icon, label, key, color, t):
    x, y = cx - w // 2, cy - h // 2
    bg = (40, 36, 72) if hot else (28, 25, 52)
    pygame.draw.rect(surf, bg, (x, y, w, h))
    border = color if hot else C_VERY_DIM
    pygame.draw.rect(surf, border, (x, y, w, h), 2)
    if hot:
        g = int(40 + 30 * math.sin(t * 6))
        glow = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
        glow.fill((*color[:3], g))
        surf.blit(glow, (x - 4, y - 4), special_flags=pygame.BLEND_PREMULTIPLIED)
    iy = y + (h - icon.get_height()) // 2
    bob = int(math.sin(t * 3 + cy) * 2)
    surf.blit(icon, (x + 10, iy + bob))
    draw_text_shadow(surf, label, font_small,
                     C_WHITE if hot else C_DIM, x + 34, cy - 6, center=False)
    kx = x + w - 12
    pygame.draw.rect(surf, (18, 16, 34), (kx - 12, cy - 8, 14, 16))
    pygame.draw.rect(surf, border, (kx - 12, cy - 8, 14, 16), 1)
    draw_text(surf, key, font_tiny, C_WHITE if hot else C_DIM, kx - 5, cy)


# ======================================================================
# MAIN GAME LOOP
# ======================================================================
def main():
    state = "MENU"
    mode = 1

    save_data = load_save()
    highest_unlocked_level = save_data["highest_unlocked_level"]
    total_stars = save_data["stars"]
    highscores = save_data["highscores"]          # {level_str: best_score}
    level_stars = save_data.get("level_stars", {})  # {level_str: stars 0-3}

    career_level = 1
    selected_level_cursor = min(highest_unlocked_level, 1)
    page = (selected_level_cursor - 1) // 10

    current_level_data = generate_career_level(1)
    game_duration = current_level_data["time_limit"]
    time_left = game_duration

    tug_balance = 0
    tug_winner = None
    tournament_mode = False
    p1_wins = 0
    p2_wins = 0
    round_number = 1

    selected_setting_idx = 0
    menu_hot_idx = 0

    particles = []
    popups = []
    shake_time = 0.0
    shake_mag = 0.0
    t_global = 0.0
    countdown = 0.0
    new_star_award = 0
    confetti_timer = 0.0

    # fever background flash helper
    def any_fever():
        return (p1 is not None and p1.fever_active) or \
               (mode == 2 and p2 is not None and p2.fever_active)

    def make_players():
        idle1, flame1 = rocket_idle, rocket_flame
        idle2, flame2 = rocket_p2_idle, rocket_p2_flame
        b1 = PlayerBar(PX_W // 2 - BAR_W // 2, C_P1, C_P1_DARK, "p1",
                       idle1, flame1,
                       cursor_speed=current_level_data["cursor_speed"],
                       target_height=current_level_data["target_height"])
        b2 = PlayerBar(PX_W - 90 - BAR_W, C_P2, C_P2_DARK, "p2",
                       idle2, flame2)
        return b1, b2

    p1, p2 = make_players()

    def reset_round():
        nonlocal time_left, p1, p2, tug_balance, tug_winner, game_duration
        nonlocal current_level_data, particles, popups, countdown
        particles = []
        popups = []
        if mode == 1:
            current_level_data = generate_career_level(career_level)
            game_duration = current_level_data["time_limit"]
            p1, _ = make_players()
            p2 = None
        else:
            game_duration = 30.0
            _, p2 = make_players()
            p1, _ = make_players()
            p1.px = 60
            p2.px = PX_W - 60 - BAR_W
            p1.base_speed = p2.base_speed = 170
            p1.cursor_speed = p2.cursor_speed = 170
            p1.target_h = p2.target_h = 40
            p1.randomize_target()
            p2.randomize_target()
        time_left = game_duration
        tug_balance = 0
        tug_winner = None
        countdown = 3.0

    def reset_full_game(selected_mode):
        nonlocal mode, p1_wins, p2_wins, round_number
        mode = selected_mode
        p1_wins = 0
        p2_wins = 0
        round_number = 1
        reset_round()

    def add_shake(mag, dur):
        nonlocal shake_mag, shake_time
        if SETTINGS["screen_shake"]:
            shake_mag = max(shake_mag, mag)
            shake_time = max(shake_time, dur)

    def _menu_activate(idx):
        """Activate a main-menu card by index (0..3)."""
        nonlocal state, selected_level_cursor, page
        if idx == 0:
            selected_level_cursor = highest_unlocked_level
            page = (selected_level_cursor - 1) // 10
            state = "LEVEL_SELECT"
        elif idx == 1:
            reset_full_game(2)
            state = "GAME"
        elif idx == 2:
            state = "CONTROLS"
        else:
            state = "SETTINGS"

    def handle_hit(bar):
        """Common reaction to a scored attempt."""
        cx_px = bar.px + BAR_W // 2
        cy_px = bar.target_y + bar.target_h // 2
        res = bar.attempt_score()
        if res in ("PERFECT", "GOOD"):
            mult = 1 + (bar.streak - 1) // 3
            if bar.fever_active:
                mult *= 2
            pts = (2 if res == "PERFECT" else 1) * mult
            popups.append(Popup(f"+{pts}", cx_px + 24, cy_px,
                                C_GOLD if res == "PERFECT" else C_GREEN,
                                big=(res == "PERFECT")))
            if res == "PERFECT":
                popups.append(Popup("PERFECT!", cx_px, cy_px - 14, C_GOLD))
                sound.play("perfect")
                spawn_burst(particles, cx_px, cy_px,
                            [C_GOLD, C_WHITE, C_FEVER_B], n=26, spread=200)
                add_shake(3, 0.15)
            else:
                sound.play("hit")
                spawn_burst(particles, cx_px, cy_px,
                            [bar.color, C_WHITE], n=14, spread=140)
            if bar.streak > 0 and bar.streak % 5 == 0:
                popups.append(Popup(f"{bar.streak} STREAK!", cx_px,
                                    cy_px - 28, C_FEVER_A, big=True))
                sound.play("coin")
                add_shake(4, 0.2)
            if bar.fever_time > 0 and bar.fever_time > 4.8:
                popups.append(Popup("FEVER!!", WIDTH // 4, HEIGHT // 4,
                                    C_FEVER_B, big=True))
                sound.play("fever")
                add_shake(5, 0.35)
        elif res == "MISS":
            sound.play("miss")
            spawn_burst(particles, cx_px, int(bar.cursor_y),
                        [C_RED, (120, 40, 40)], n=12, spread=120)
            add_shake(6, 0.3)
        return res

    # ------------------------------------------------------------------
    while True:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 0.05)
        t_global += dt
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                key = event.key
                # -------- MENU --------
                if state == "MENU":
                    if key in (pygame.K_UP, pygame.K_w):
                        menu_hot_idx = (menu_hot_idx - 1) % len(MENU_ITEMS)
                        sound.play("back")
                    elif key in (pygame.K_DOWN, pygame.K_s):
                        menu_hot_idx = (menu_hot_idx + 1) % len(MENU_ITEMS)
                        sound.play("select")
                    elif key in (pygame.K_RETURN, pygame.K_SPACE):
                        # activate the highlighted card via shared handler
                        _menu_activate(menu_hot_idx)
                        sound.play("select")
                    elif key == pygame.K_1:
                        selected_level_cursor = highest_unlocked_level
                        page = (selected_level_cursor - 1) // 10
                        state = "LEVEL_SELECT"
                        sound.play("select")
                    elif key == pygame.K_2:
                        reset_full_game(2)
                        state = "GAME"
                        sound.play("select")
                    elif key == pygame.K_3:
                        state = "CONTROLS"
                        sound.play("select")
                    elif key == pygame.K_4:
                        state = "SETTINGS"
                        sound.play("select")
                    elif key == pygame.K_t:
                        tournament_mode = not tournament_mode
                        sound.play("select")
                    elif key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

                # -------- LEVEL SELECT --------
                elif state == "LEVEL_SELECT":
                    if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        sound.play("back")
                        state = "MENU"
                    elif key == pygame.K_LEFT:
                        selected_level_cursor = max(1, selected_level_cursor - 1)
                        sound.play("back")
                    elif key == pygame.K_RIGHT:
                        selected_level_cursor = min(highest_unlocked_level,
                                                    selected_level_cursor + 1)
                        sound.play("select")
                    elif key == pygame.K_UP:
                        selected_level_cursor = max(1, selected_level_cursor - 5)
                        sound.play("back")
                    elif key == pygame.K_DOWN:
                        selected_level_cursor = min(highest_unlocked_level,
                                                    selected_level_cursor + 5)
                        sound.play("select")
                    elif key in (pygame.K_SPACE, pygame.K_RETURN):
                        sound.play("select")
                        career_level = selected_level_cursor
                        reset_full_game(1)
                        state = "GAME"
                    page = (selected_level_cursor - 1) // 10

                # -------- SETTINGS --------
                elif state == "SETTINGS":
                    if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        sound.play("back")
                        state = "MENU"
                    elif key == pygame.K_UP:
                        selected_setting_idx = (selected_setting_idx - 1) % len(SETTING_KEYS)
                        sound.play("back")
                    elif key == pygame.K_DOWN:
                        selected_setting_idx = (selected_setting_idx + 1) % len(SETTING_KEYS)
                        sound.play("select")
                    elif key in (pygame.K_SPACE, pygame.K_RETURN):
                        k = SETTING_KEYS[selected_setting_idx]
                        SETTINGS[k] = not SETTINGS[k]
                        if k == "sound":
                            sound.enabled = SETTINGS["sound"] and sound.mixer_ok
                        sound.play("select")

                # -------- CONTROLS --------
                elif state == "CONTROLS":
                    if key in (pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                        sound.play("back")
                        state = "MENU"

                # -------- IN-GAME --------
                elif state == "GAME":
                    if countdown > 0:
                        continue
                    if key == pygame.K_a or key == pygame.K_SPACE:
                        if mode == 1 or True:
                            res = handle_hit(p1)
                            if mode == 2 and res in ("PERFECT", "GOOD"):
                                power = 1 + (p1.streak // 3)
                                if p1.fever_active:
                                    power += 1
                                tug_balance -= power
                    if mode == 2 and key == pygame.K_l:
                        res = handle_hit(p2)
                        if res in ("PERFECT", "GOOD"):
                            power = 1 + (p2.streak // 3)
                            if p2.fever_active:
                                power += 1
                            tug_balance += power
                    if key == pygame.K_ESCAPE:
                        sound.play("back")
                        state = "MENU"

                # -------- RESULT SCREENS --------
                elif state in ("LEVEL_CLEAR", "ROUND_OVER", "GAMEOVER",
                               "TOURNAMENT_OVER", "NEW RECORD"):
                    if key in (pygame.K_SPACE, pygame.K_RETURN):
                        sound.play("select")
                        if state == "LEVEL_CLEAR" or state == "NEW RECORD":
                            career_level += 1
                            if career_level > highest_unlocked_level:
                                highest_unlocked_level = career_level
                            reset_round()
                            state = "GAME"
                        elif state == "ROUND_OVER":
                            round_number += 1
                            reset_round()
                            state = "GAME"
                        else:
                            reset_full_game(mode)
                            state = "GAME"
                    elif key == pygame.K_ESCAPE:
                        sound.play("back")
                        state = "MENU"

        # ------------------------------------------------------------------
        # UPDATE
        # ------------------------------------------------------------------
        for p in particles[:]:
            p.update(dt)
            if p.life <= 0:
                particles.remove(p)
        for pu in popups[:]:
            pu.update(dt)
            if pu.life <= 0:
                popups.remove(pu)
        if shake_time > 0:
            shake_time -= dt
            if shake_time <= 0:
                shake_mag = 0

        if state == "GAME":
            if countdown > 0:
                countdown -= dt
            else:
                time_left -= dt
                p1.update(dt)
                p1.update_timers(dt)
                if mode == 2 and p2:
                    p2.update(dt)
                    p2.update_timers(dt)

                round_ended = False
                if mode == 1:
                    if p1.lives <= 0:
                        sound.play("crash")
                        add_shake(8, 0.5)
                        spawn_burst(particles, p1.px + BAR_W // 2,
                                    int(p1.cursor_y),
                                    [C_RED, C_GOLD, C_WHITE], n=40, spread=240)
                        state = "GAMEOVER"
                        sound.play("lose")
                    elif time_left <= 0:
                        time_left = 0
                        if p1.score >= current_level_data["target_score"]:
                            state = "LEVEL_CLEAR"
                        else:
                            state = "GAMEOVER"
                            sound.play("lose")
                    elif p1.score >= current_level_data["target_score"]:
                        # level cleared!
                        st = stars_for(current_level_data, p1)
                        prev_best = int(highscores.get(str(career_level), 0))
                        new_record = p1.score > prev_best
                        highscores[str(career_level)] = max(prev_best, p1.score)
                        if career_level == highest_unlocked_level:
                            highest_unlocked_level = min(LEVEL_COUNT,
                                                         career_level + 1)
                        key = str(career_level)
                        prev_stars = int(level_stars.get(key, 0))
                        if st > prev_stars:
                            total_stars += st - prev_stars
                            level_stars[key] = st
                        save_data = {
                            "highest_unlocked_level": highest_unlocked_level,
                            "stars": total_stars,
                            "highscores": highscores,
                            "level_stars": level_stars,
                        }
                        write_save(save_data)
                        sound.play("win")
                        confetti_timer = 1.2
                        state = "NEW RECORD" if new_record else "LEVEL_CLEAR"
                else:
                    KO_TARGET = 12
                    if tug_balance <= -KO_TARGET:
                        tug_winner = "P1 KNOCKOUT!"
                        round_ended = True
                    elif tug_balance >= KO_TARGET:
                        tug_winner = "P2 KNOCKOUT!"
                        round_ended = True
                    elif p1.lives <= 0 or p2.lives <= 0:
                        tug_winner = ("P2 WINS - P1 DOWN!" if p1.lives <= 0
                                      else "P1 WINS - P2 DOWN!")
                        round_ended = True
                    elif time_left <= 0:
                        time_left = 0
                        round_ended = True

                    if round_ended:
                        add_shake(8, 0.5)
                        if tournament_mode:
                            rw = None
                            if tug_winner:
                                rw = "p1" if tug_winner.startswith("P1") else "p2"
                            elif tug_balance < 0:
                                rw = "p1"
                            elif tug_balance > 0:
                                rw = "p2"
                            if rw == "p1":
                                p1_wins += 1
                            elif rw == "p2":
                                p2_wins += 1
                            if p1_wins >= 2 or p2_wins >= 2:
                                state = "TOURNAMENT_OVER"
                                sound.play("win")
                            else:
                                state = "ROUND_OVER"
                                sound.play("coin")
                        else:
                            state = "GAMEOVER"
                            sound.play("win")

        if confetti_timer > 0 and state in ("LEVEL_CLEAR", "NEW RECORD"):
            confetti_timer -= dt
            for _ in range(3):
                particles.append(Particle(random.uniform(0, PX_W), -4,
                                          random.choice([C_GOLD, C_P1, C_P2,
                                                         C_GREEN, C_FEVER_A]),
                                          vx=random.uniform(-30, 30),
                                          vy=random.uniform(40, 120),
                                          life=random.uniform(1.0, 2.0),
                                          gravity=60))

        # ------------------------------------------------------------------
        # RENDER (everything into the low-res pixel buffer)
        # ------------------------------------------------------------------
        buffer.fill(C_BG_TOP)
        draw_background(buffer, t_global, fever=any_fever() and state == "GAME")

        if state == "MENU":
            # big title with rocket
            bob = int(math.sin(t_global * 2) * 4)
            ti = font_large.render("TIMING CLASH", True, C_GOLD)
            shadow = font_large.render("TIMING CLASH", True, (90, 60, 10))
            tw = ti.get_width()
            buffer.blit(shadow, (PX_W // 2 - tw // 2 + 2, 34 + bob // 2 + 2))
            buffer.blit(ti, (PX_W // 2 - tw // 2, 34 + bob // 2))
            buffer.blit(rocket_idle, (PX_W // 2 - tw // 2 - 20, 30 + bob))
            buffer.blit(rocket_p2_idle, (PX_W // 2 + tw // 2 + 9, 30 - bob))
            draw_text(buffer, "PIXEL ARCADE EDITION", font_tiny, C_P1,
                      PX_W // 2, 68)

            mouse_idx = -1
            card_h, gap = 34, 8
            start_y = 120
            for i, (k, label, col, icon) in enumerate(MENU_ITEMS):
                cy = start_y + i * (card_h + gap) + card_h // 2
                hx = PX_W // 2
                rect = pygame.Rect(hx - 110, cy - card_h // 2, 220, card_h)
                if rect.collidepoint(mx // PIXEL_SCALE, my // PIXEL_SCALE):
                    mouse_idx = i
                hot = (i == menu_hot_idx) or (i == mouse_idx)
                draw_menu_card(buffer, hx, cy, 220, card_h, hot, icon,
                               label, k, col, t_global)
            menu_hot_idx = mouse_idx if mouse_idx >= 0 else menu_hot_idx

            # footer stats
            draw_text(buffer, f"TOTAL STARS: {total_stars}", font_tiny,
                      C_GOLD, PX_W // 2 - 90, PX_H - 46)
            best_any = max([int(v) for v in highscores.values()] or [0])
            draw_text(buffer, f"BEST SCORE: {best_any}", font_tiny,
                      C_P1, PX_W // 2 + 90, PX_H - 46)
            t_stat = "ON" if tournament_mode else "OFF"
            draw_text(buffer, f"[T] BEST OF 3: {t_stat}", font_tiny,
                      C_GREEN if tournament_mode else C_DIM,
                      PX_W // 2, PX_H - 28)
            draw_text(buffer, "ARROWS + ENTER  |  or press number keys",
                      font_tiny, C_DIM, PX_W // 2, PX_H - 12)

        elif state == "LEVEL_SELECT":
            draw_text_shadow(buffer, "SELECT MISSION", font_medium, C_GOLD,
                             PX_W // 2, 20)
            draw_text(buffer, f"STARS: {total_stars}   LEVELS: "
                              f"{highest_unlocked_level}/{LEVEL_COUNT}",
                      font_tiny, C_DIM, PX_W // 2, 40)

            grid_cols, box_w, box_h = 5, 62, 44
            gx0 = PX_W // 2 - (grid_cols * box_w + (grid_cols - 1) * 6) // 2
            gy0 = 58
            page_first = page * 10 + 1
            for slot in range(10):
                lvl = page_first + slot
                col_i, row_i = slot % grid_cols, slot // grid_cols
                bx = gx0 + col_i * (box_w + 6)
                by = gy0 + row_i * (box_h + 6)
                unlocked = lvl <= highest_unlocked_level
                sel = lvl == selected_level_cursor
                if unlocked:
                    st = int(level_stars.get(str(lvl), 0))
                    bgc = (52, 44, 92) if sel else (32, 28, 58)
                    pygame.draw.rect(buffer, bgc, (bx, by, box_w, box_h))
                    bc = C_GOLD if sel else C_VERY_DIM
                    pygame.draw.rect(buffer, bc, (bx, by, box_w, box_h),
                                     2 if sel else 1)
                    draw_text(buffer, str(lvl), font_small,
                              C_WHITE if sel else C_DIM,
                              bx + box_w // 2, by + 12)
                    sx = bx + box_w // 2 - (st * 7) - 1
                    for si in range(3):
                        icon = star_on if si < st else star_off
                        blit_col = (sx + si * 9, by + box_h - 14)
                        if unlocked:
                            buffer.blit(icon, blit_col)
                else:
                    pygame.draw.rect(buffer, (22, 20, 38), (bx, by, box_w, box_h))
                    pygame.draw.rect(buffer, (40, 38, 60), (bx, by, box_w, box_h), 1)
                    buffer.blit(skull_icon, (bx + box_w // 2 - 3, by + box_h // 2 - 4))

            # info panel
            pv = generate_career_level(selected_level_cursor)
            if selected_level_cursor <= highest_unlocked_level:
                best = int(highscores.get(str(selected_level_cursor), 0))
                info = (f"GOAL {pv['target_score']} PTS   TIME {int(pv['time_limit'])}s"
                        f"   SPEED {pv['cursor_speed']}   BEST {best}")
                draw_text(buffer, info, font_tiny, C_P1, PX_W // 2, PX_H - 40)
            else:
                draw_text(buffer, "LOCKED - CLEAR PREVIOUS MISSIONS",
                          font_tiny, C_RED, PX_W // 2, PX_H - 40)
            draw_text(buffer, "<- Arrows navigate | SPACE launch | ESC back | A/D page",
                      font_tiny, C_DIM, PX_W // 2, PX_H - 20)
            draw_text(buffer, f"PAGE {page + 1}/3", font_tiny, C_GOLD,
                      PX_W - 40, 20)

        elif state == "SETTINGS":
            draw_text_shadow(buffer, "SETTINGS", font_medium, C_GOLD,
                             PX_W // 2, 30)
            for i, k in enumerate(SETTING_KEYS):
                yy = 70 + i * 26
                sel = i == selected_setting_idx
                col = C_WHITE if sel else C_DIM
                pre = "> " if sel else "  "
                draw_text(buffer, f"{pre}{SETTING_LABELS[k]}", font_small,
                          col, PX_W // 2 - 110, yy, center=False)
                vc = C_GREEN if SETTINGS[k] else C_RED
                draw_text(buffer, "[ ON ]" if SETTINGS[k] else "[ OFF ]",
                          font_small, vc, PX_W // 2 + 110, yy)
            draw_text(buffer, "UP/DOWN move | SPACE toggle | ESC back",
                      font_tiny, C_DIM, PX_W // 2, PX_H - 30)

        elif state == "CONTROLS":
            draw_text_shadow(buffer, "HOW TO PLAY", font_medium, C_GOLD,
                             PX_W // 2, 24)
            rowy = 60
            draw_text(buffer, "LAND THE ROCKET INSIDE THE GLOWING TARGET ZONE",
                      font_tiny, C_WHITE, PX_W // 2, rowy)
            rowy += 18
            draw_text(buffer, "CENTER OF THE ZONE = PERFECT = DOUBLE POINTS",
                      font_tiny, C_GOLD, PX_W // 2, rowy)
            rowy += 18
            draw_text(buffer, "CHAIN HITS FOR STREAKS  x2  x3  x4 ...",
                      font_tiny, C_GREEN, PX_W // 2, rowy)
            rowy += 18
            buffer.blit(zap_icon, (PX_W // 2 - 60, rowy - 6))
            draw_text(buffer, "FILL THE COMBO METER TO TRIGGER FEVER MODE (2x PTS!)",
                      font_tiny, C_FEVER_B, PX_W // 2 + 12, rowy)
            rowy += 20
            buffer.blit(heart_full, (PX_W // 2 - 78, rowy - 6))
            draw_text(buffer, "A MISS COSTS ONE LIFE AND FREEZES YOUR ROCKET",
                      font_tiny, C_RED, PX_W // 2 + 14, rowy)
            rowy += 24
            # keycaps
            buffer.blit(keycap_blue, (PX_W // 2 - 100, rowy))
            draw_text(buffer, "= PLAYER 1 / SOLO", font_tiny, C_P1,
                      PX_W // 2 + 10, rowy + 7)
            rowy += 20
            buffer.blit(keycap_red, (PX_W // 2 - 100, rowy))
            draw_text(buffer, "= PLAYER 2 (TUG OF WAR)", font_tiny, C_P2,
                      PX_W // 2 + 24, rowy + 7)
            rowy += 26
            draw_text(buffer, "SPACE also works for solo timing. Press ESC/SPACE to return",
                      font_tiny, C_DIM, PX_W // 2, PX_H - 30)

        elif state == "GAME":
            # HUD
            if mode == 1:
                lv = current_level_data
                draw_text_shadow(buffer, lv["title"], font_small, C_GOLD,
                                 PX_W // 2, 12)
                # goal progress bar
                goal_frac = min(1.0, p1.score / max(1, lv["target_score"]))
                gw = 160
                gx = PX_W // 2 - gw // 2
                pygame.draw.rect(buffer, (30, 26, 55), (gx, 22, gw, 8))
                fillc = C_GREEN if goal_frac >= 1 else C_P1
                pygame.draw.rect(buffer, fillc, (gx, 22, int(gw * goal_frac), 8))
                pygame.draw.rect(buffer, C_VERY_DIM, (gx, 22, gw, 8), 1)
                draw_text(buffer, f"{p1.score}/{lv['target_score']}", font_tiny,
                          C_WHITE, PX_W // 2, 36)

                # timer
                tc = C_RED if time_left < 5 else C_WHITE
                draw_text_shadow(buffer, f"{math.ceil(time_left)}", font_medium,
                                 tc, PX_W - 34, 16)
                draw_text(buffer, "SEC", font_tiny, C_DIM, PX_W - 34, 34)

                # lives (hearts, top-left)
                for li in range(3):
                    icon = heart_full if li < p1.lives else heart_empty
                    buffer.blit(icon, (10 + li * 11, 10))

                # streak + fever meter (left column)
                if p1.streak >= 2:
                    mult = 1 + p1.streak // 3
                    draw_text_shadow(buffer, f"x{mult}", font_small,
                                     C_FEVER_A, 24, 40)
                    draw_text(buffer, f"{p1.streak} STRK", font_tiny, C_DIM,
                              24, 52)
                # fever meter vertical, right of bar
                fx = p1.px + BAR_W + 6
                fh = BAR_H
                pygame.draw.rect(buffer, (30, 26, 55), (fx, BAR_Y, 5, fh))
                fill_h = int(fh * (1.0 if p1.fever_time > 0 else p1.fever))
                fc = C_FEVER_B if p1.fever_time > 0 else C_GOLD
                pygame.draw.rect(buffer, fc,
                                 (fx, BAR_Y + fh - fill_h, 5, fill_h))
                pygame.draw.rect(buffer, C_VERY_DIM, (fx, BAR_Y, 5, fh), 1)
                if int(t_global * 6) % 2 == 0 and p1.fever_time > 0:
                    draw_text(buffer, "FEVER!", font_tiny, C_FEVER_A,
                              fx + 2, BAR_Y - 8)
                else:
                    draw_text(buffer, "ZAP", font_tiny, C_DIM, fx + 2, BAR_Y - 8)

                p1.draw(buffer, particles, popups, t_global)

            else:
                # ---- TUG OF WAR ----
                draw_text_shadow(buffer, "TUG OF WAR", font_small, C_GOLD,
                                 PX_W // 2, 12)
                if tournament_mode:
                    draw_text(buffer, f"ROUND {round_number}   "
                                      f"P1 {p1_wins} - {p2_wins} P2",
                              font_tiny, C_DIM, PX_W // 2, 26)
                tc = C_RED if time_left < 5 else C_WHITE
                draw_text_shadow(buffer, f"{math.ceil(time_left)}", font_medium,
                                 tc, PX_W // 2, 40)

                # rope + flag
                rope_y = PX_H // 2 + 60
                pygame.draw.line(buffer, (150, 110, 60),
                                 (30, rope_y), (PX_W - 30, rope_y), 2)
                for nx in range(34, PX_W - 30, 8):
                    pygame.draw.line(buffer, (110, 80, 45),
                                     (nx, rope_y - 2), (nx, rope_y + 2))
                flag_x = PX_W // 2 + int(tug_balance * 6.5)
                pygame.draw.rect(buffer, C_WHITE, (flag_x - 1, rope_y - 12, 2, 24))
                pygame.draw.polygon(buffer, C_GOLD,
                                    [(flag_x + 1, rope_y - 12),
                                     (flag_x + 11, rope_y - 8),
                                     (flag_x + 1, rope_y - 4)])
                # win zones
                pygame.draw.rect(buffer, (*C_P1[:3],), (30, rope_y - 6, 14, 12))
                pygame.draw.rect(buffer, C_P2, (PX_W - 44, rope_y - 6, 14, 12))

                # per-player HUD
                for bar, xoff, colr, tag in ((p1, 10, C_P1, "P1"),
                                             (p2, PX_W - 10, C_P2, "P2")):
                    if bar is None:
                        continue
                    draw_text_shadow(buffer, f"{tag}: {bar.score}", font_small,
                                     colr, xoff + (0 if tag == 'P1' else 0), 40)
                    for li in range(3):
                        icon = heart_full if li < bar.lives else heart_empty
                        if tag == "P1":
                            buffer.blit(icon, (xoff + li * 11, 52))
                        else:
                            buffer.blit(icon, (xoff - 9 - li * 11, 52))
                    # mini fever bar
                    fxm = xoff if tag == "P1" else xoff - 40
                    pygame.draw.rect(buffer, (30, 26, 55), (fxm, 64, 40, 4))
                    ffill = int(40 * (1.0 if bar.fever_time > 0 else bar.fever))
                    pygame.draw.rect(buffer,
                                     C_FEVER_B if bar.fever_time > 0 else C_GOLD,
                                     (fxm, 64, ffill, 4))
                    if bar.streak >= 2:
                        draw_text(buffer, f"x{1 + bar.streak // 3}", font_tiny,
                                  C_FEVER_A, fxm + 20, 76)

                p1.draw(buffer, particles, popups, t_global)
                if p2:
                    p2.draw(buffer, particles, popups, t_global)

            # particles & popups on top
            if SETTINGS["particles"]:
                for p in particles:
                    p.draw(buffer)
            for pu in popups:
                pu.draw(buffer)

            if SETTINGS["show_fps"]:
                draw_text(buffer, f"{int(clock.get_fps())} FPS", font_tiny,
                          C_GREEN, PX_W - 30, PX_H - 10)

            # countdown overlay
            if countdown > 0:
                n = math.ceil(countdown)
                txt = str(n) if n > 0 else "GO!"
                draw_text_shadow(buffer, txt, font_giant,
                                 C_GOLD if n <= 0 else C_WHITE,
                                 PX_W // 2, PX_H // 2)

        elif state in ("LEVEL_CLEAR", "NEW RECORD", "GAMEOVER", "ROUND_OVER",
                       "TOURNAMENT_OVER"):
            # keep last frame dimmed behind
            ov = pygame.Surface((PX_W, PX_H), pygame.SRCALPHA)
            ov.fill((10, 8, 24, 190))
            buffer.blit(ov, (0, 0))

            if SETTINGS["particles"]:
                for p in particles:
                    p.draw(buffer)

            if state in ("LEVEL_CLEAR", "NEW RECORD"):
                buffer.blit(trophy_icon, (PX_W // 2 - 5, 60))
                draw_text_shadow(buffer, "MISSION COMPLETE!", font_large,
                                 C_GREEN, PX_W // 2, 110)
                if state == "NEW RECORD":
                    if int(t_global * 4) % 2 == 0:
                        draw_text_shadow(buffer, "* NEW RECORD *", font_medium,
                                         C_FEVER_A, PX_W // 2, 145)
                st = stars_for(current_level_data, p1)
                for si in range(3):
                    icon = star_on if si < st else star_off
                    buffer.blit(icon, (PX_W // 2 - 16 + si * 12, 160))
                draw_text(buffer, f"SCORE {p1.score}   PERFECTS {p1.perfects}"
                                  f"   BEST STREAK {p1.best_streak}",
                          font_tiny, C_WHITE, PX_W // 2, 196)
                draw_text(buffer, f"NEXT: LEVEL {min(career_level + 1, LEVEL_COUNT)} UNLOCKED",
                          font_tiny, C_GOLD, PX_W // 2, 214)
                draw_text(buffer, "SPACE: Next Level   |   ESC: Menu",
                          font_tiny, C_DIM, PX_W // 2, PX_H - 30)

            elif state == "TOURNAMENT_OVER":
                buffer.blit(trophy_icon, (PX_W // 2 - 5, 60))
                champ = "PLAYER 1" if p1_wins > p2_wins else "PLAYER 2"
                cc = C_P1 if p1_wins > p2_wins else C_P2
                draw_text_shadow(buffer, "CHAMPION!", font_large, C_GOLD,
                                 PX_W // 2, 110)
                draw_text_shadow(buffer, f"{champ} TAKES THE CROWN", font_medium,
                                 cc, PX_W // 2, 150)
                draw_text(buffer, f"FINAL  {p1_wins} - {p2_wins}", font_small,
                          C_WHITE, PX_W // 2, 185)
                draw_text(buffer, "SPACE: Rematch   |   ESC: Menu", font_tiny,
                          C_DIM, PX_W // 2, PX_H - 30)

            elif state == "ROUND_OVER":
                winner_txt = tug_winner if tug_winner else (
                    "P1 TAKES THE ROUND" if tug_balance < 0 else
                    "P2 TAKES THE ROUND" if tug_balance > 0 else " DEAD HEAT!")
                wc = C_P1 if "P1" in winner_txt else C_P2 if "P2" in winner_txt else C_WHITE
                draw_text_shadow(buffer, f"ROUND {round_number} OVER", font_large,
                                 C_WHITE, PX_W // 2, 110)
                draw_text_shadow(buffer, winner_txt, font_medium, wc,
                                 PX_W // 2, 155)
                draw_text(buffer, f"SERIES  P1 {p1_wins} - {p2_wins} P2",
                          font_small, C_GOLD, PX_W // 2, 190)
                draw_text(buffer, "SPACE: Next Round   |   ESC: Menu", font_tiny,
                          C_DIM, PX_W // 2, PX_H - 30)

            else:  # GAMEOVER
                buffer.blit(skull_icon, (PX_W // 2 - 4, 60))
                if mode == 1:
                    reason = "ROCKET DESTROYED!" if p1.lives <= 0 else "TIME'S UP!"
                    draw_text_shadow(buffer, "MISSION FAILED", font_large,
                                     C_RED, PX_W // 2, 110)
                    draw_text(buffer, reason, font_small, C_WHITE,
                              PX_W // 2, 145)
                    need = current_level_data["target_score"]
                    draw_text(buffer, f"SCORE {p1.score} / {need} NEEDED",
                              font_small, C_GOLD, PX_W // 2, 170)
                else:
                    res = tug_winner or (
                        "PLAYER 1 WINS!" if tug_balance < 0 else
                        "PLAYER 2 WINS!" if tug_balance > 0 else "A PERFECT TIE!")
                    rc = (C_P1 if "1" in res and "2" not in res else
                          C_P2 if "2" in res else C_WHITE)
                    draw_text_shadow(buffer, "MATCH OVER", font_large, C_WHITE,
                                     PX_W // 2, 110)
                    draw_text_shadow(buffer, res, font_medium, rc,
                                     PX_W // 2, 155)
                draw_text(buffer, "SPACE: Retry   |   ESC: Menu", font_tiny,
                          C_DIM, PX_W // 2, PX_H - 30)

        # ------------------------------------------------------------------
        # BLIT BUFFER -> SCREEN (with screen shake, nearest-neighbour scaling)
        # ------------------------------------------------------------------
        ox = oy = 0
        if SETTINGS["screen_shake"] and shake_time > 0:
            ox = random.randint(-int(shake_mag), int(shake_mag))
            oy = random.randint(-int(shake_mag), int(shake_mag))
        scaled = pygame.transform.scale_by(buffer, PIXEL_SCALE)
        screen.fill((0, 0, 0))
        screen.blit(scaled, (ox, oy))
        pygame.display.flip()


if __name__ == "__main__":
    main()
