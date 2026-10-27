#!/usr/bin/env python3
"""
TIMING CLASH  -  a pixel-art timing battler
===========================================

Single file, no assets.  Every sprite, font, background and sound is generated
in code.  The only dependency is pygame:

    pip install pygame
    python timing_clash.py

MODES
  CAMPAIGN   Fight through endless levels.  Every 5th level is a boss, every
             5 levels is a new world.  Earn up to 3 stars per level.
  SURVIVAL   One heart pool, endless waves.  Chase your best wave and score.
  VERSUS 2P  Local duel on one keyboard.  P1 = A, P2 = L.  Best of 1 / 3 / 5.

HOW TO PLAY
  A line bounces up and down a bar.  Hit SPACE (or A, or click) while it is
  inside the green zone.  The gold centre is a PERFECT hit (double damage).
  Miss and the bar locks while the enemy's RAGE meter charges.  When the
  meter fills, it hits you.  Every 5-hit streak is a POWER STRIKE that also
  heals a heart.

F11 = fullscreen   M = mute   P / ESC = pause

Also runs in the browser via Pyodide (see index.html for the GitHub Pages launcher).
"""
import asyncio
import colorsys
import json
import math
import os
import random
import sys
import threading
from array import array

try:
    import pygame
except ImportError:  # pragma: no cover
    sys.exit("Timing Clash needs pygame.\nInstall it with:  pip install pygame")

# --------------------------------------------------------------------------
#  CONSTANTS
# --------------------------------------------------------------------------
W, H = 320, 180            # internal pixel resolution (scaled up to the window)
FPS = 60
FLOOR_Y = 132              # top of the ground
GROUND = 150               # y where characters' feet rest
BAR_TOP, BAR_H = 30, 100   # timing bar geometry
RATE = 22050               # audio sample rate
SAVE_NAME = "timing_clash_save.json"
WEB = sys.platform == "emscripten"   # running inside Pyodide / a browser

# DawnBringer 16 palette: every colour in the game comes from here
PAL = [
    (20, 12, 28), (68, 36, 52), (48, 52, 109), (78, 74, 78),
    (133, 76, 48), (52, 101, 36), (208, 70, 72), (117, 113, 97),
    (89, 125, 206), (210, 125, 44), (133, 149, 161), (109, 170, 44),
    (210, 170, 153), (109, 194, 202), (218, 212, 94), (222, 238, 214),
]
(INK, WINE, NAVY, CHAR, BROWN, FOREST, RED, STONE,
 BLUE, ORANGE, STEEL, GREEN, SKIN, CYAN, YELLOW, WHITE) = PAL

DEFAULT_SETTINGS = {
    "difficulty": 1, "music": True, "sfx": True, "shake": True,
    "particles": True, "show_fps": False, "vs_rounds": 3, "fullscreen": False,
}
DIFFICULTY = [
    {"name": "EASY", "hearts": 6, "lock": 0.45, "gauge": 1.45},
    {"name": "NORMAL", "hearts": 5, "lock": 0.80, "gauge": 1.00},
    {"name": "HARD", "hearts": 4, "lock": 1.30, "gauge": 0.72},
]
WORLD_NAMES = ["GREEN MEADOW", "DARK CAVE", "OLD CASTLE", "FIRE PEAK", "THE VOID"]


# --------------------------------------------------------------------------
#  SAVE DATA  (compatible with the old save: "highest_unlocked_level")
# --------------------------------------------------------------------------
class SaveData:
    def __init__(self):
        here = os.path.dirname(os.path.abspath(__file__))
        self.paths = [os.path.join(here, SAVE_NAME),
                      os.path.join(os.path.expanduser("~"), "." + SAVE_NAME)]
        if WEB:
            self.paths = ["/persist/" + SAVE_NAME]
        self.highest = 1
        self.stars = {}
        self.survival_best = 0
        self.survival_wave = 0
        self.settings = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        for p in self.paths:
            if not os.path.exists(p):
                continue
            try:
                with open(p, "r") as f:
                    d = json.load(f)
                self.highest = max(1, int(d.get("highest_unlocked_level", 1)))
                self.stars = {str(k): int(v) for k, v in d.get("stars", {}).items()}
                self.survival_best = int(d.get("survival_best", 0))
                self.survival_wave = int(d.get("survival_wave", 0))
                for k, v in d.get("settings", {}).items():
                    if k in DEFAULT_SETTINGS and type(v) is type(DEFAULT_SETTINGS[k]):
                        self.settings[k] = v
                return
            except Exception:
                continue

    def save(self):
        payload = {
            "highest_unlocked_level": self.highest, "stars": self.stars,
            "survival_best": self.survival_best, "survival_wave": self.survival_wave,
            "settings": self.settings,
        }
        for p in self.paths:
            try:
                with open(p, "w") as f:
                    json.dump(payload, f, indent=1)
                return
            except OSError:
                continue

    def star_count(self, level):
        return self.stars.get(str(level), 0)

    def record_level(self, level, stars):
        self.highest = max(self.highest, level + 1)
        if stars > self.star_count(level):
            self.stars[str(level)] = stars
        self.save()

    def reset(self):
        self.highest, self.stars = 1, {}
        self.survival_best = self.survival_wave = 0
        self.save()


# --------------------------------------------------------------------------
#  PIXEL FONT  (5x7 bitmap, uppercase only)
# --------------------------------------------------------------------------
_FONT_SRC = {
    "A": ".###. #...# #...# ##### #...# #...# #...#",
    "B": "####. #...# #...# ####. #...# #...# ####.",
    "C": ".###. #...# #.... #.... #.... #...# .###.",
    "D": "####. #...# #...# #...# #...# #...# ####.",
    "E": "##### #.... #.... ####. #.... #.... #####",
    "F": "##### #.... #.... ####. #.... #.... #....",
    "G": ".###. #...# #.... #.### #...# #...# .###.",
    "H": "#...# #...# #...# ##### #...# #...# #...#",
    "I": ".###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.",
    "J": "..### ...#. ...#. ...#. ...#. #..#. .##..",
    "K": "#...# #..#. #.#.. ##... #.#.. #..#. #...#",
    "L": "#.... #.... #.... #.... #.... #.... #####",
    "M": "#...# ##.## #.#.# #.#.# #...# #...# #...#",
    "N": "#...# ##..# #.#.# #..## #...# #...# #...#",
    "O": ".###. #...# #...# #...# #...# #...# .###.",
    "P": "####. #...# #...# ####. #.... #.... #....",
    "Q": ".###. #...# #...# #...# #.#.# #..#. .##.#",
    "R": "####. #...# #...# ####. #.#.. #..#. #...#",
    "S": ".#### #.... #.... .###. ....# ....# ####.",
    "T": "##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..",
    "U": "#...# #...# #...# #...# #...# #...# .###.",
    "V": "#...# #...# #...# #...# #...# .#.#. ..#..",
    "W": "#...# #...# #...# #.#.# #.#.# ##.## #...#",
    "X": "#...# #...# .#.#. ..#.. .#.#. #...# #...#",
    "Y": "#...# #...# .#.#. ..#.. ..#.. ..#.. ..#..",
    "Z": "##### ....# ...#. ..#.. .#... #.... #####",
    "0": ".###. #...# #..## #.#.# ##..# #...# .###.",
    "1": "..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.",
    "2": ".###. #...# ....# ...#. ..#.. .#... #####",
    "3": ".###. #...# ....# ..##. ....# #...# .###.",
    "4": "...#. ..##. .#.#. #..#. ##### ...#. ...#.",
    "5": "##### #.... ####. ....# ....# #...# .###.",
    "6": "..##. .#... #.... ####. #...# #...# .###.",
    "7": "##### ....# ...#. ..#.. .#... .#... .#...",
    "8": ".###. #...# #...# .###. #...# #...# .###.",
    "9": ".###. #...# #...# .#### ....# ...#. .##..",
    ".": "..... ..... ..... ..... ..... .##.. .##..",
    ",": "..... ..... ..... ..... .##.. ..#.. .#...",
    "!": "..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..",
    "?": ".###. #...# ....# ...#. ..#.. ..... ..#..",
    ":": "..... .##.. .##.. ..... .##.. .##.. .....",
    "-": "..... ..... ..... .###. ..... ..... .....",
    "+": "..... ..#.. ..#.. ##### ..#.. ..#.. .....",
    "/": "....# ....# ...#. ..#.. .#... #.... #....",
    "(": "..#.. .#... #.... #.... #.... .#... ..#..",
    ")": "..#.. ...#. ....# ....# ....# ...#. ..#..",
    "'": "..#.. ..#.. .#... ..... ..... ..... .....",
    "%": "##..# ##..# ...#. ..#.. .#... #..## #..##",
    "*": "..... #.#.# .###. ##### .###. #.#.# .....",
    "<": "...#. ..#.. .#... #.... .#... ..#.. ...#.",
    ">": ".#... ..#.. ...#. ....# ...#. ..#.. .#...",
    "=": "..... ..... ##### ..... ##### ..... .....",
    "[": "###.. #.... #.... #.... #.... #.... ###..",
    "]": "..### ....# ....# ....# ....# ....# ..###",
    " ": ".....  .....  .....  .....  .....  .....  .....",
}
FONT = {ch: src.split() for ch, src in _FONT_SRC.items()}
FONT[" "] = ["....."] * 7

_text_cache = {}


def text_width(text, scale=1):
    return max(0, len(text) * 6 * scale - scale)


def text_surf(text, color, scale=1, shadow=None):
    key = (text, color, scale, shadow)
    img = _text_cache.get(key)
    if img is not None:
        return img
    if len(_text_cache) > 700:
        _text_cache.clear()
    soff = 0
    if shadow:
        soff = scale if scale <= 2 else max(1, scale // 2)
    w = max(1, text_width(text, scale) + soff)
    h = 7 * scale + soff
    img = pygame.Surface((w, h), pygame.SRCALPHA)
    passes = [(shadow, soff), (color, 0)] if shadow else [(color, 0)]
    for col, off in passes:
        for i, ch in enumerate(text.upper()):
            rows = FONT.get(ch)
            if not rows:
                continue
            for ry, row in enumerate(rows):
                for rx, c in enumerate(row):
                    if c == "#":
                        img.fill(col, (i * 6 * scale + rx * scale + off,
                                       ry * scale + off, scale, scale))
    _text_cache[key] = img
    return img


def draw_text(surf, text, x, y, color=WHITE, scale=1, align="left", shadow=INK):
    img = text_surf(str(text), color, scale, shadow)
    if align == "center":
        x -= img.get_width() // 2
    elif align == "right":
        x -= img.get_width()
    surf.blit(img, (int(x), int(y)))
    return img.get_width()


# --------------------------------------------------------------------------
#  SPRITES  (hex digit = index into the 16-colour palette, '.' = clear)
# --------------------------------------------------------------------------
def sym(half):
    return [r + r[::-1] for r in half]


HERO = [
    "......66......f.",
    ".....666.....fa.",
    "....000000...fa.",
    "...0aafffa0..fa.",
    "...0aaaaaaa0.fa.",
    "...0aa00000a0fa.",
    "...0aaaaaaaa0fa.",
    "....0aaaaaa0.fa.",
    "...008888880.fa.",
    "..0c0e8888820fa.",
    "..0c08888882eeee",
    "...0088888882.4.",
    "....02222220.4..",
    "....0222222.0...",
    "....04400440....",
    "...0440.0440....",
]

SLIME = [
    "................",
    "................",
    "................",
    "................",
    "......0000......",
    "....00bbbb00....",
    "...0bbfbbbbb0...",
    "..0bbfbbbbbbb0..",
    "..0bbbbbbbbbb0..",
    ".0bbffbbbbffbb0.",
    ".0bb0fbbbb0fbb0.",
    ".0bbbbbbbbbbbb0.",
    ".0bbbbbbbbbbbb0.",
    ".05bbbbbbbbbb50.",
    "..055bbbbbb550..",
    "...0055555500...",
]

BAT = sym([
    "........",
    "........",
    "........",
    "......0.",
    "0....030",
    "00..0333",
    "0100.0e3",
    "01110333",
    "011110.3",
    "0111110.",
    ".010110.",
    "..0.0.0.",
    "........",
    "........",
    "........",
    "........",
])

GOBLIN = sym([
    "........",
    "........",
    "....0000",
    "..00bbbb",
    "00.0bbbb",
    "0b0bbbbb",
    "0bb0b6bb",
    ".0bbbbbb",
    "..0bb00b",
    "...0bbbb",
    "..044444",
    ".0444444",
    ".0b44444",
    "..044.04",
    "..0440.0",
    "..000.00",
])

SKULL = sym([
    "........",
    "....0000",
    "...0ffff",
    "..0fffff",
    "..0fffff",
    "..0f000f",
    "..0f000f",
    "..0ffff0",
    "..00ffff",
    "...0f0f0",
    "...00000",
    "....0aaf",
    "...0afaa",
    "...0aaff",
    "....0aaa",
    "...00a00",
])

GHOST = sym([
    "........",
    "....0000",
    "...0ffff",
    "..0fffff",
    "..0fffff",
    "..0ff00f",
    "..0ff00f",
    "..0fffff",
    "..0fff00",
    "..0dffff",
    "..0dffff",
    "..0ddfff",
    "..0dddff",
    "..0d0ddf",
    "...00d0d",
    "....0.0.",
])

GOLEM = sym([
    "........",
    "........",
    "....0000",
    "...07777",
    "...07ee7",
    "...07777",
    "..000777",
    ".0a07777",
    "0aa0a777",
    "0aa0a7a7",
    "0a00a777",
    ".0.07777",
    "...07a7a",
    "...07777",
    "...0770.",
    "..00000.",
])

ENEMY_ART = {"slime": SLIME, "bat": BAT, "goblin": GOBLIN,
             "skull": SKULL, "ghost": GHOST, "golem": GOLEM}

HEART = [".66.66.", "6f66666", "6666666", ".66666.", "..666..", "...6..."]
STAR = ["...e...", "..eee..", "eeeeeee", ".eeeee.", "..eee..", ".ee.ee.", ".e...e."]
LOCK = ["..aaa..", ".a...a.", ".a...a.", "aaaaaaa", "aa333aa", "aa333aa", "aaaaaaa"]
SKULL_ICON = [".fffff.", "f0fff0f", "f0fff0f", ".fffff.", "..f.f..", "..fff.."]

_spr_cache = {}
_sil_cache = {}


def shift_hue(c, hue):
    h, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
    if s < 0.3:
        return c
    r, g, b = colorsys.hsv_to_rgb((h + hue) % 1.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def make_sprite(rows, hue=0.0, remap=None):
    h = len(rows)
    w = max(len(r) for r in rows)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            if remap and ch in remap:
                ch = remap[ch]
            c = PAL[int(ch, 16)]
            if hue:
                c = shift_hue(c, hue)
            surf.set_at((x, y), c)
    return surf


def silhouette(surf, color):
    key = (id(surf), color)
    s = _sil_cache.get(key)
    if s is None:
        mask = pygame.mask.from_surface(surf)
        s = mask.to_surface(setcolor=color + (255,), unsetcolor=(0, 0, 0, 0))
        _sil_cache[key] = s
    return s


def outlined(surf, color=INK):
    w, h = surf.get_size()
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    sil = silhouette(surf, color)
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(sil, (dx, dy))
    out.blit(surf, (1, 1))
    return out


def hero_sprite(player=0):
    key = ("hero", player)
    if key not in _spr_cache:
        if player == 0:
            _spr_cache[key] = make_sprite(HERO)
        else:
            remap = {"8": "6", "2": "1", "6": "e", "e": "b"}
            _spr_cache[key] = pygame.transform.flip(make_sprite(HERO, remap=remap), True, False)
    return _spr_cache[key]


def enemy_sprite(kind, hue=0.0, scale=1):
    key = ("enemy", kind, round(hue, 2), scale)
    if key not in _spr_cache:
        s = make_sprite(ENEMY_ART[kind], hue)
        if scale > 1:
            s = pygame.transform.scale(s, (s.get_width() * scale, s.get_height() * scale))
        _spr_cache[key] = s
    return _spr_cache[key]


def icon(name, empty=False):
    key = ("icon", name, empty)
    if key not in _spr_cache:
        data = {"heart": HEART, "star": STAR, "lock": LOCK, "skull": SKULL_ICON}[name]
        remap = None
        if empty:
            remap = {"6": "3", "f": "3", "e": "3"}
        elif name == "star":
            remap = {"e": "e"}
        _spr_cache[key] = outlined(make_sprite(data, remap=remap))
    return _spr_cache[key]


def big_icon(name, empty=False, scale=2):
    key = ("bigicon", name, empty, scale)
    if key not in _spr_cache:
        i = icon(name, empty)
        _spr_cache[key] = pygame.transform.scale(i, (i.get_width() * scale, i.get_height() * scale))
    return _spr_cache[key]


_shadow_cache = {}


def draw_shadow(s, cx, y, w):
    img = _shadow_cache.get(w)
    if img is None:
        img = pygame.Surface((w, 4), pygame.SRCALPHA)
        pygame.draw.ellipse(img, (20, 12, 28, 110), (0, 0, w, 4))
        _shadow_cache[w] = img
    s.blit(img, (cx - w // 2, y - 2))


def blit_char(s, spr, left, feet, flash=None, alpha=255, flip=False):
    img = silhouette(spr, flash) if flash else spr
    if flip:
        img = pygame.transform.flip(img, True, False)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    s.blit(img, (int(left), int(feet - spr.get_height())))


# --------------------------------------------------------------------------
#  UI HELPERS
# --------------------------------------------------------------------------
def panel(s, rect, fill=NAVY, alpha=None):
    x, y, w, h = rect
    if alpha is not None:
        tmp = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(tmp, fill + (alpha,), (0, 0, w, h))
        s.blit(tmp, (x, y))
    else:
        pygame.draw.rect(s, fill, rect)
    pygame.draw.rect(s, INK, rect, 1)
    pygame.draw.rect(s, STEEL, (x + 1, y + 1, w - 3, 1))
    pygame.draw.rect(s, STEEL, (x + 1, y + 1, 1, h - 3))
    pygame.draw.rect(s, CHAR, (x + 1, y + h - 2, w - 2, 1))
    pygame.draw.rect(s, CHAR, (x + w - 2, y + 1, 1, h - 2))


def keycap(s, label, cx, y, color=WHITE):
    w = text_width(label) + 7
    x = cx - w // 2
    pygame.draw.rect(s, INK, (x, y, w, 11))
    pygame.draw.rect(s, STEEL, (x + 1, y + 1, w - 2, 8))
    pygame.draw.rect(s, CHAR, (x + 1, y + 9, w - 2, 1))
    draw_text(s, label, cx, y + 2, INK, align="center", shadow=None)


def bar_gauge(s, x, y, w, h, frac, fill, back=CHAR, hi=WHITE):
    pygame.draw.rect(s, INK, (x - 1, y - 1, w + 2, h + 2))
    pygame.draw.rect(s, back, (x, y, w, h))
    fw = int(round(w * max(0.0, min(1.0, frac))))
    if fw > 0:
        pygame.draw.rect(s, fill, (x, y, fw, h))
        if h >= 4:
            pygame.draw.rect(s, hi, (x, y, fw, 1))


# --------------------------------------------------------------------------
#  BACKGROUNDS  (pre-rendered once per theme)
# --------------------------------------------------------------------------
def banded(s, y0, y1, colors):
    """Vertical colour bands with a 4-row dithered blend between them."""
    n = len(colors)
    bh = (y1 - y0) / n
    for i, c in enumerate(colors):
        ya, yb = int(y0 + i * bh), int(y0 + (i + 1) * bh)
        pygame.draw.rect(s, c, (0, ya, W, yb - ya))
    for i in range(n - 1):
        c, nc = colors[i], colors[i + 1]
        if c == nc:
            continue
        yb = int(y0 + (i + 1) * bh)
        for dy, mod, col, off in ((-2, 4, nc, 0), (-1, 2, nc, 0), (0, 2, c, 1), (1, 4, c, 1)):
            for x in range(W):
                if x % mod == off and 0 <= yb + dy < H:
                    s.set_at((x, yb + dy), col)


def hills(s, color, base, amp, freq, phase):
    for x in range(W):
        y = base + int(amp * math.sin(x * freq + phase) + amp * 0.5 * math.sin(x * freq * 2.3 + phase * 2))
        pygame.draw.line(s, color, (x, y), (x, FLOOR_Y))


def cloud(s, x, y):
    for dx, dy, w, h in ((0, 4, 30, 6), (4, 1, 20, 6), (14, 0, 14, 5), (-3, 6, 36, 3)):
        pygame.draw.rect(s, WHITE, (x + dx, y + dy, w, h))
    pygame.draw.rect(s, CYAN, (x - 3, y + 9, 36, 1))


def _bg_meadow(s):
    banded(s, 0, FLOOR_Y, [BLUE, BLUE, CYAN, CYAN, WHITE])
    pygame.draw.circle(s, YELLOW, (262, 34), 12)
    pygame.draw.circle(s, WHITE, (262, 34), 7)
    for cx, cy in ((30, 28), (118, 50), (196, 20), (284, 70)):
        cloud(s, cx, cy)
    hills(s, STEEL, 100, 14, 0.021, 0.5)
    hills(s, GREEN, 114, 8, 0.034, 2.0)
    hills(s, FOREST, 124, 4, 0.05, 4.0)
    rng = random.Random(3)
    for tx in (14, 40, 288, 306):          # little pine trees
        for i in range(4):
            pygame.draw.rect(s, FOREST, (tx - 3 - i * 2, 92 + i * 9, 7 + i * 4, 9))
            pygame.draw.rect(s, GREEN, (tx - 3 - i * 2, 92 + i * 9, 7 + i * 4, 1))
        pygame.draw.rect(s, BROWN, (tx - 1, 128, 3, 4))
    pygame.draw.rect(s, GREEN, (0, FLOOR_Y, W, 3))
    pygame.draw.rect(s, FOREST, (0, FLOOR_Y + 3, W, 2))
    pygame.draw.rect(s, BROWN, (0, FLOOR_Y + 5, W, H))
    for _ in range(90):
        x, y = rng.randrange(W), rng.randrange(FLOOR_Y + 7, H)
        s.set_at((x, y), rng.choice((CHAR, ORANGE)))
    for x in range(0, W, 6):
        pygame.draw.rect(s, GREEN, (x + rng.randrange(3), FLOOR_Y - 2, 1, 2))


def _bg_cave(s):
    banded(s, 0, FLOOR_Y, [INK, INK, WINE, WINE])
    rng = random.Random(5)
    for _ in range(46):                      # rock wall blobs
        x, y = rng.randrange(W), rng.randrange(20, FLOOR_Y - 6)
        pygame.draw.rect(s, rng.choice((CHAR, INK, WINE)), (x, y, rng.randrange(6, 20), rng.randrange(3, 8)))
    for x in range(-4, W, 22):               # stalactites
        x += rng.randrange(8)
        hgt = rng.randrange(14, 40)
        pygame.draw.polygon(s, CHAR, [(x, 0), (x + 16, 0), (x + 8, hgt)])
        pygame.draw.polygon(s, INK, [(x + 8, 0), (x + 16, 0), (x + 8, hgt)])
    pygame.draw.rect(s, CHAR, (0, FLOOR_Y, W, 4))
    pygame.draw.rect(s, STONE, (0, FLOOR_Y, W, 1))
    pygame.draw.rect(s, INK, (0, FLOOR_Y + 4, W, H))
    for y in range(FLOOR_Y + 4, H, 11):
        pygame.draw.rect(s, CHAR, (0, y, W, 1))
        off = (y // 11) % 2 * 16
        for x in range(off, W, 32):
            pygame.draw.rect(s, CHAR, (x, y, 1, 11))
    for x in range(10, W, 40):               # stalagmites
        h2 = rng.randrange(6, 16)
        pygame.draw.polygon(s, CHAR, [(x, FLOOR_Y), (x + 10, FLOOR_Y), (x + 5, FLOOR_Y - h2)])


def _bg_castle(s):
    pygame.draw.rect(s, CHAR, (0, 0, W, FLOOR_Y))
    for row, y in enumerate(range(0, FLOOR_Y, 10)):
        pygame.draw.rect(s, INK, (0, y, W, 1))
        for x in range((row % 2) * 12 - 12, W, 24):
            pygame.draw.rect(s, INK, (x, y, 1, 10))
            pygame.draw.rect(s, STONE, (x + 1, y + 1, 22, 1))
    for wx in (46, 138, 226):                # arched windows
        pygame.draw.rect(s, INK, (wx - 1, 29, 30, 50))
        pygame.draw.rect(s, NAVY, (wx + 1, 40, 26, 38))
        pygame.draw.circle(s, INK, (wx + 14, 40), 15)
        pygame.draw.circle(s, NAVY, (wx + 14, 40), 13)
        pygame.draw.rect(s, BLUE, (wx + 1, 56, 26, 1))
        pygame.draw.rect(s, INK, (wx + 13, 28, 2, 50))
    for bx in (12, 96, 182, 270):            # banners
        pygame.draw.rect(s, INK, (bx - 1, 6, 20, 44))
        pygame.draw.rect(s, RED, (bx, 6, 18, 40))
        pygame.draw.polygon(s, RED, [(bx, 46), (bx + 18, 46), (bx + 9, 54)])
        pygame.draw.rect(s, YELLOW, (bx + 7, 14, 4, 12))
        pygame.draw.rect(s, YELLOW, (bx + 4, 18, 10, 4))
    pygame.draw.rect(s, STONE, (0, FLOOR_Y, W, 2))
    pygame.draw.rect(s, STEEL, (0, FLOOR_Y + 2, W, H))
    for i, y in enumerate(range(FLOOR_Y + 2, H, 9)):
        for x in range(-16 * (i % 2), W, 32):
            pygame.draw.rect(s, STONE, (x, y, 16, 9))
        pygame.draw.rect(s, CHAR, (0, y, W, 1))


def _bg_volcano(s):
    banded(s, 0, FLOOR_Y, [INK, WINE, WINE, RED, ORANGE])
    rng = random.Random(9)
    for cx, hgt, wid in ((60, 70, 90), (170, 90, 110), (270, 60, 80)):
        pygame.draw.polygon(s, INK, [(cx - wid, FLOOR_Y), (cx, FLOOR_Y - hgt), (cx + wid, FLOOR_Y)])
        pygame.draw.polygon(s, WINE, [(cx - 6, FLOOR_Y - hgt + 6), (cx, FLOOR_Y - hgt), (cx + 6, FLOOR_Y - hgt + 6)])
        pygame.draw.rect(s, ORANGE, (cx - 2, FLOOR_Y - hgt, 4, 2))
    for _ in range(60):
        s.set_at((rng.randrange(W), rng.randrange(0, 60)), rng.choice((ORANGE, YELLOW, RED)))
    pygame.draw.rect(s, INK, (0, FLOOR_Y, W, H))
    pygame.draw.rect(s, ORANGE, (0, FLOOR_Y, W, 1))
    for i in range(14):                      # lava cracks
        x, y = rng.randrange(W), rng.randrange(FLOOR_Y + 4, H - 2)
        for _ in range(rng.randrange(4, 9)):
            pygame.draw.rect(s, rng.choice((ORANGE, RED)), (x, y, 2, 1))
            x += rng.choice((-2, 2, 2))
            y += rng.choice((0, 1, 1))
    for x in range(0, W, 9):
        pygame.draw.rect(s, CHAR, (x, FLOOR_Y + 1, 5, 1))


def _bg_void(s):
    banded(s, 0, FLOOR_Y, [INK, INK, NAVY, NAVY, WINE])
    rng = random.Random(13)
    for _ in range(90):
        s.set_at((rng.randrange(W), rng.randrange(FLOOR_Y)), rng.choice((WHITE, CYAN, STEEL, STEEL)))
    pygame.draw.circle(s, BLUE, (74, 52), 24)
    pygame.draw.circle(s, NAVY, (82, 58), 18)
    pygame.draw.circle(s, INK, (74, 52), 24, 1)
    pygame.draw.ellipse(s, STEEL, (36, 46, 76, 14), 1)
    pygame.draw.circle(s, CYAN, (260, 30), 5)
    pygame.draw.rect(s, INK, (0, FLOOR_Y, W, H))
    pygame.draw.rect(s, CYAN, (0, FLOOR_Y, W, 1))
    for i in range(1, 7):                    # perspective grid
        y = FLOOR_Y + int((i / 6) ** 1.8 * (H - FLOOR_Y))
        pygame.draw.rect(s, NAVY, (0, y, W, 1))
    for x in range(-W, 2 * W, 34):
        pygame.draw.line(s, NAVY, (W // 2 + (x - W // 2) // 4, FLOOR_Y), (x, H))


_BG_BUILDERS = [_bg_meadow, _bg_cave, _bg_castle, _bg_volcano, _bg_void]
_bg_cache = {}


def get_bg(theme):
    theme %= len(_BG_BUILDERS)
    if theme not in _bg_cache:
        s = pygame.Surface((W, H))
        _BG_BUILDERS[theme](s)
        _bg_cache[theme] = s
    return _bg_cache[theme]


class Ambient:
    """Drifting particles + flickering torches for each theme."""

    def __init__(self, theme):
        self.theme = theme % 5
        self.t = 0.0
        rng = random.Random(self.theme + 77)
        self.p = [[rng.uniform(0, W), rng.uniform(10, FLOOR_Y), rng.uniform(0.5, 1.5), rng.random() * 6.28]
                  for _ in range(24)]
        self.glow = pygame.Surface((56, 56), pygame.SRCALPHA)
        for r, a in ((26, 22), (18, 30), (10, 40)):
            pygame.draw.circle(self.glow, (210, 125, 44, a), (28, 28), r)

    def update(self, dt):
        self.t += dt
        th = self.theme
        for p in self.p:
            if th == 0:
                p[0] = (p[0] + 10 * p[2] * dt) % W
                p[1] += math.sin(self.t + p[3]) * 4 * dt
            elif th == 1:
                p[0] += math.cos(self.t * p[2] + p[3]) * 8 * dt
                p[1] += math.sin(self.t * p[2] * 0.7 + p[3]) * 6 * dt
            elif th == 2:
                p[1] -= 3 * p[2] * dt
                if p[1] < 0:
                    p[1] = FLOOR_Y
            elif th == 3:
                p[1] -= 22 * p[2] * dt
                p[0] += math.sin(self.t * 2 + p[3]) * 10 * dt
                if p[1] < 0:
                    p[1] = FLOOR_Y + 10
            else:
                pass

    def draw(self, s, particles=True):
        th = self.theme
        if th in (1, 2):
            for tx in (68, 252):
                flick = int(self.t * 9 + tx) % 3
                s.blit(self.glow, (tx - 28, 52 - 28 - flick))
                pygame.draw.rect(s, INK, (tx - 2, 60, 5, 12))
                pygame.draw.rect(s, BROWN, (tx - 1, 60, 3, 12))
                pygame.draw.rect(s, ORANGE, (tx - 2, 52 - flick, 5, 8 + flick))
                pygame.draw.rect(s, YELLOW, (tx - 1, 55 - flick, 3, 5 + flick))
                pygame.draw.rect(s, WHITE, (tx, 58, 1, 2))
        if not particles:
            return
        colors = [WHITE, YELLOW, STEEL, ORANGE, CYAN][th]
        for p in self.p:
            x, y = int(p[0]) % W, int(p[1])
            if th == 4 and math.sin(self.t * 3 + p[3]) < 0:
                continue
            if th == 1:
                col = CYAN if math.sin(self.t * 4 + p[3]) > -0.3 else NAVY
            elif th == 3:
                col = ORANGE if p[2] > 1 else YELLOW
            else:
                col = colors
            s.set_at((x, y), col)
            if th in (0, 1) and p[2] > 1.2:
                s.set_at((x + 1, y), col)


# --------------------------------------------------------------------------
#  AUDIO  (all sounds are synthesised at start-up; music builds in a thread)
# --------------------------------------------------------------------------
def _wave(kind, ph):
    p = ph % 1.0
    if kind == "sq":
        return 1.0 if p < 0.5 else -1.0
    if kind == "pulse":
        return 1.0 if p < 0.25 else -1.0
    if kind == "tri":
        return 4.0 * abs(p - 0.5) - 1.0
    if kind == "saw":
        return 2.0 * p - 1.0
    return random.uniform(-1.0, 1.0)


def render_note(freq, dur, kind="sq", vol=0.3, slide=0.0, decay=1.0):
    n = max(1, int(RATE * dur))
    out = [0.0] * n
    ph = 0.0
    for i in range(n):
        ph += (freq + slide * (i / n)) / RATE
        env = (1.0 - i / n) ** decay if decay else 1.0
        if i < 60:
            env *= i / 60.0
        out[i] = _wave(kind, ph) * vol * env
    return out


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


SFX_DEFS = {
    "select": [(880, 0.04, "sq", 0.18)],
    "confirm": [(523, 0.05, "sq", 0.2), (784, 0.09, "sq", 0.2)],
    "back": [(392, 0.05, "sq", 0.18), (262, 0.07, "sq", 0.18)],
    "good": [(660, 0.10, "pulse", 0.28, 330)],
    "perfect": [(midi(72), 0.05, "pulse", 0.28), (midi(76), 0.05, "pulse", 0.28),
                (midi(79), 0.05, "pulse", 0.28), (midi(84), 0.14, "pulse", 0.28)],
    "power": [(300, 0.25, "sq", 0.25, 900), (midi(84), 0.18, "tri", 0.3)],
    "miss": [(220, 0.22, "saw", 0.25, -140)],
    "locked": [(150, 0.04, "sq", 0.12)],
    "hurt": [(0, 0.25, "noise", 0.34, 0, 1.5), (130, 0.2, "saw", 0.25, -70)],
    "thud": [(0, 0.06, "noise", 0.3), (160, 0.1, "sq", 0.25, -90)],
    "heal": [(midi(72), 0.07, "tri", 0.3), (midi(76), 0.07, "tri", 0.3), (midi(79), 0.12, "tri", 0.3)],
    "ko": [(0, 0.45, "noise", 0.3, 0, 1.3), (200, 0.4, "saw", 0.2, -150)],
    "win": [(midi(72), 0.1, "pulse", 0.28), (midi(76), 0.1, "pulse", 0.28), (midi(79), 0.1, "pulse", 0.28),
            (midi(84), 0.32, "pulse", 0.3)],
    "lose": [(midi(67), 0.18, "sq", 0.25), (midi(63), 0.18, "sq", 0.25), (midi(60), 0.18, "sq", 0.25),
             (midi(55), 0.45, "saw", 0.25, -30)],
    "tick": [(440, 0.08, "sq", 0.2)],
    "go": [(880, 0.25, "pulse", 0.3)],
    "rage": [(180, 0.12, "saw", 0.2, 120), (240, 0.12, "saw", 0.2, 160)],
}


class Audio:
    def __init__(self, app):
        self.app = app
        self.ok = False
        self.sounds = {}
        self.music_snd = None
        self.music_chan = None
        self.muted = False
        self._gen = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            freq, fmt, ch = pygame.mixer.get_init()
            if fmt != -16:
                return
            self.channels = ch
            self.ok = True
            for name, notes in SFX_DEFS.items():
                samples = []
                for n in notes:
                    f, d, kind, vol = n[0], n[1], n[2], n[3]
                    slide = n[4] if len(n) > 4 else 0.0
                    decay = n[5] if len(n) > 5 else 1.0
                    samples += render_note(f, d, kind, vol, slide, decay)
                snd = self._to_sound(samples)
                snd.set_volume(0.55)
                self.sounds[name] = snd
            self._gen = self._music_steps()
            if not WEB:     # desktop: build in a background thread
                gen = self._gen
                self._gen = None
                threading.Thread(target=lambda: [None for _ in gen], daemon=True).start()
        except Exception:
            self.ok = False

    def _to_sound(self, samples):
        buf = array("h")
        two = self.channels == 2
        for v in samples:
            iv = int(max(-1.0, min(1.0, v)) * 30000)
            buf.append(iv)
            if two:
                buf.append(iv)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _music_steps(self):
        try:
            bpm = 138
            eighth = 60.0 / bpm / 2
            n8 = int(RATE * eighth)
            chords = [([57, 60, 64], 45), ([53, 57, 60], 41), ([48, 52, 55], 48), ([55, 59, 62], 43)]
            lead = [81, 79, 76, 79, 77, 76, 72, 76, 79, 76, 72, 76, 74, 71, 74, 79]
            bars = 8
            total = [0.0] * (bars * 8 * n8)

            def mix(start, samples):
                for i, v in enumerate(samples):
                    if start + i < len(total):
                        total[start + i] += v

            li = 0
            for bar in range(bars):
                chord, root = chords[(bar // 2) % 4]
                for e in range(8):
                    pos = (bar * 8 + e) * n8
                    arp = chord[[0, 1, 2, 1, 0, 1, 2, 1][e]] + 12
                    mix(pos, render_note(midi(arp), eighth * 0.9, "pulse", 0.07, 0, 1.2))
                    if e % 4 == 0:
                        mix(pos, render_note(midi(root), eighth * 3.6, "tri", 0.2, 0, 0.5))
                    if e in (0, 3, 6):
                        mix(pos, render_note(midi(lead[li % len(lead)]), eighth * 1.8, "sq", 0.07, 0, 1.0))
                        li += 1
                    if e % 2 == 1:
                        mix(pos, render_note(0, 0.03, "noise", 0.05, 0, 2.0))
                    if e in (0, 4):
                        mix(pos, render_note(120, 0.08, "sq", 0.12, -70, 2.0))
                    yield
            snd = self._to_sound(total)
            snd.set_volume(0.32)
            self.music_snd = snd
            if self.app.cfg["music"] and not self.muted:
                self._start_music()
        except Exception:
            pass

    def pump(self):
        """Browser only: advance music synthesis a little each frame."""
        if self._gen is not None:
            try:
                next(self._gen)
            except StopIteration:
                self._gen = None
            except Exception:
                self._gen = None

    def _start_music(self):
        if self.music_snd is not None and self.music_chan is None:
            self.music_chan = self.music_snd.play(loops=-1)

    def set_music(self, on):
        if not self.ok:
            return
        if on and not self.muted:
            self._start_music()
        elif self.music_chan is not None:
            self.music_chan.stop()
            self.music_chan = None
            if self.music_snd:
                self.music_snd.stop()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.set_music(False)
        else:
            self.set_music(self.app.cfg["music"])

    def play(self, name):
        if self.ok and self.app.cfg["sfx"] and not self.muted:
            snd = self.sounds.get(name)
            if snd:
                snd.play()


# --------------------------------------------------------------------------
#  EFFECTS: particles, floating text, projectiles
# --------------------------------------------------------------------------
class Projectile:
    def __init__(self, x0, y0, x1, y1, speed, color, on_hit):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        d = math.hypot(x1 - x0, y1 - y0)
        self.dur = max(0.08, d / speed)
        self.t = 0.0
        self.color = color
        self.on_hit = on_hit
        self.x, self.y = x0, y0
        self.done = False


class FX:
    def __init__(self, app):
        self.app = app
        self.parts, self.texts, self.shots = [], [], []

    def burst(self, x, y, color, n=12, speed=90, life=0.5, grav=140, size=2):
        if not self.app.cfg["particles"]:
            return
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.3, 1.0) * speed
            self.parts.append([x, y, math.cos(a) * sp, math.sin(a) * sp - 20, random.uniform(0.5, 1.0) * life,
                               life, random.choice((1, size)), color])

    def text(self, txt, x, y, color=WHITE, scale=1, life=0.9):
        self.texts.append([txt, x, y, life, life, color, scale])

    def shot(self, x0, y0, x1, y1, speed, color, on_hit):
        self.shots.append(Projectile(x0, y0, x1, y1, speed, color, on_hit))

    def update(self, dt):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 140 * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        for t in self.texts:
            t[2] -= 14 * dt
            t[3] -= dt
        self.texts = [t for t in self.texts if t[3] > 0]
        for sh in self.shots:
            sh.t += dt
            f = min(1.0, sh.t / sh.dur)
            sh.x = sh.x0 + (sh.x1 - sh.x0) * f
            sh.y = sh.y0 + (sh.y1 - sh.y0) * f
            if self.app.cfg["particles"] and random.random() < 0.8:
                self.parts.append([sh.x, sh.y, random.uniform(-15, 15), random.uniform(-15, 15), 0.25, 0.25, 1, sh.color])
            if f >= 1.0:
                sh.done = True
                sh.on_hit()
        self.shots = [sh for sh in self.shots if not sh.done]

    def draw(self, s):
        for p in self.parts:
            col = p[7] if p[4] > p[5] * 0.35 else STEEL
            s.fill(col, (int(p[0]), int(p[1]), p[6], p[6]))
        for sh in self.shots:
            x, y = int(sh.x), int(sh.y)
            pygame.draw.rect(s, INK, (x - 4, y - 2, 9, 5))
            pygame.draw.rect(s, sh.color, (x - 3, y - 1, 7, 3))
            pygame.draw.rect(s, WHITE, (x - 1, y - 1, 3, 1))
        for t in self.texts:
            if t[3] < 0.25 and int(t[3] * 40) % 2 == 0:
                continue
            draw_text(s, t[0], t[1], t[2], t[5], t[6], "center")


# --------------------------------------------------------------------------
#  TIMING BAR  (the heart of the game)
# --------------------------------------------------------------------------
class TimingBar:
    W = 16

    def __init__(self, x, top=BAR_TOP, h=BAR_H, color=YELLOW):
        self.x, self.top, self.h, self.color = x, top, h, color
        self.scale = 1.0
        self.configure(0.6, 0.3, [], 0.8)

    def configure(self, speed, zone, mods, lock):
        self.base_speed = speed
        self.speed_mult = 1.0
        self.base_zone = self.zone = zone
        self.mods = set(mods)
        self.lock_time = lock
        self.pos = random.random()
        self.dir = 1
        self.lock = 0.0
        self.t = 0.0
        self.flip_t = random.uniform(1.0, 2.2)
        self.drift_dir = random.choice((-1, 1))
        self.zone_c = 0.5
        self.decoy_c = None
        self.flash = 0.0
        self.place_zone()

    def speed(self):
        return min(self.base_speed * self.speed_mult * self.scale, 1.75)

    def place_zone(self):
        half = self.zone / 2
        c = 0.5
        for _ in range(30):
            c = random.uniform(half + 0.03, 1 - half - 0.03)
            if abs(c - self.pos) > 0.22 and abs(c - self.zone_c) > 0.12:
                break
        self.zone_c = c
        self.decoy_c = None
        if "decoy" in self.mods:
            dh = self.zone * 0.7
            for _ in range(30):
                d = random.uniform(dh / 2 + 0.03, 1 - dh / 2 - 0.03)
                if abs(d - c) > half + dh / 2 + 0.07:
                    self.decoy_c = d
                    break

    def visible(self):
        return "blink" not in self.mods or (self.t % 2.2) < 1.3

    def update(self, dt):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.lock > 0:
            self.lock -= dt
            return
        if "flip" in self.mods:
            self.flip_t -= dt
            if self.flip_t <= 0:
                self.dir *= -1
                self.flip_t = random.uniform(1.2, 2.6)
        spd = self.speed()
        if "erratic" in self.mods:
            spd *= 1 + 0.45 * math.sin(self.t * 3.3)
        self.pos += self.dir * spd * dt
        if self.pos <= 0:
            self.pos, self.dir = 0.0, 1
        elif self.pos >= 1:
            self.pos, self.dir = 1.0, -1
        if "drift" in self.mods:
            half = self.zone / 2
            self.zone_c += self.drift_dir * 0.13 * dt
            if self.zone_c < half + 0.02:
                self.zone_c, self.drift_dir = half + 0.02, 1
            elif self.zone_c > 1 - half - 0.02:
                self.zone_c, self.drift_dir = 1 - half - 0.02, -1

    def press(self):
        """Returns None (locked), 'perfect', 'good', 'miss' or 'decoy'."""
        if self.lock > 0:
            return None
        half = self.zone / 2
        d = abs(self.pos - self.zone_c)
        if d <= half:
            perfect = d <= half * 0.34
            self.speed_mult = min(self.speed_mult + 0.03, 1.5)
            if "shrink" in self.mods:
                self.zone = max(0.10, self.zone * 0.92)
            self.flash = 0.12
            self.place_zone()
            return "perfect" if perfect else "good"
        res = "miss"
        if self.decoy_c is not None and abs(self.pos - self.decoy_c) <= self.zone * 0.35:
            res = "decoy"
        self.lock = self.lock_time
        self.speed_mult = 1.0
        self.zone = self.base_zone
        return res

    def cursor_y(self):
        return self.top + int(round(self.pos * self.h))

    def draw(self, s, show_zone=True):
        x, top, h, w = self.x, self.top, self.h, self.W
        pygame.draw.rect(s, INK, (x - 4, top - 4, w + 8, h + 8))
        pygame.draw.rect(s, STEEL, (x - 3, top - 3, w + 6, h + 6))
        pygame.draw.rect(s, WHITE, (x - 3, top - 3, w + 6, 1))
        pygame.draw.rect(s, CHAR, (x - 3, top + h + 2, w + 6, 1))
        pygame.draw.rect(s, INK, (x - 1, top - 1, w + 2, h + 2))
        pygame.draw.rect(s, NAVY, (x, top, w, h))
        for i in range(1, 10):
            ty = top + i * h // 10
            pygame.draw.rect(s, CHAR, (x, ty, 3, 1))
            pygame.draw.rect(s, CHAR, (x + w - 3, ty, 3, 1))
        if show_zone:
            if self.decoy_c is not None:
                dh = max(3, int(self.zone * 0.7 * h))
                dy = top + int((self.decoy_c - self.zone * 0.35) * h)
                for i in range(dh):
                    pygame.draw.rect(s, RED if i % 2 == 0 else WINE, (x + 1, dy + i, w - 2, 1))
                pygame.draw.rect(s, INK, (x + 1, dy, w - 2, 1))
                pygame.draw.rect(s, INK, (x + 1, dy + dh - 1, w - 2, 1))
            if self.visible():
                zy0 = top + int(round((self.zone_c - self.zone / 2) * h))
                zy1 = top + int(round((self.zone_c + self.zone / 2) * h))
                zh = max(3, zy1 - zy0)
                pygame.draw.rect(s, FOREST, (x, zy0, w, zh))
                pygame.draw.rect(s, GREEN, (x + 1, zy0 + 1, w - 2, max(1, zh - 2)))
                ph = max(2, int(round(zh * 0.34)))
                py = zy0 + (zh - ph) // 2
                pygame.draw.rect(s, YELLOW, (x + 1, py, w - 2, ph))
                pygame.draw.rect(s, WHITE, (x + 1, py, w - 2, 1))
                if self.flash > 0:
                    pygame.draw.rect(s, WHITE, (x, zy0, w, zh))
            else:
                for yy in range(top + 2, top + h - 2, 8):   # faint hint it's still there
                    if (self.t * 6) % 2 < 1:
                        s.set_at((x + 1, yy), FOREST)
        cy = self.cursor_y()
        locked = self.lock > 0
        col = RED if locked and int(self.t * 16) % 2 == 0 else (STEEL if locked else WHITE)
        cap = RED if locked else self.color
        pygame.draw.rect(s, INK, (x - 7, cy - 2, w + 14, 5))
        pygame.draw.rect(s, col, (x - 6, cy - 1, w + 12, 3))
        pygame.draw.rect(s, INK, (x - 11, cy - 4, 5, 9))
        pygame.draw.rect(s, INK, (x + w + 6, cy - 4, 5, 9))
        pygame.draw.rect(s, cap, (x - 10, cy - 3, 3, 7))
        pygame.draw.rect(s, cap, (x + w + 7, cy - 3, 3, 7))


# --------------------------------------------------------------------------
#  LEVEL GENERATION
# --------------------------------------------------------------------------
ENEMIES = [
    {"kind": "slime", "name": "SLIME", "mods": [], "hp": 1.0, "boss": "SLIME KING"},
    {"kind": "bat", "name": "BAT", "mods": ["erratic"], "hp": 0.9, "boss": "BAT LORD"},
    {"kind": "goblin", "name": "GOBLIN", "mods": ["drift"], "hp": 1.1, "boss": "GOBLIN CHIEF"},
    {"kind": "skull", "name": "SKELETON", "mods": ["decoy"], "hp": 1.0, "boss": "THE LICH"},
    {"kind": "ghost", "name": "GHOST", "mods": ["blink"], "hp": 0.9, "boss": "PHANTOM"},
    {"kind": "golem", "name": "GOLEM", "mods": ["shrink"], "hp": 1.3, "boss": "TITAN"},
]
MOD_TEXT = {
    "erratic": "WILD SPEED", "drift": "DRIFTING ZONE", "decoy": "RED TRAP ZONE",
    "blink": "VANISHING ZONE", "shrink": "SHRINKING ZONE", "flip": "SUDDEN REVERSE",
}
TIER_PREFIX = ["", "ANGRY ", "ELITE ", "DEADLY ", "ANCIENT "]
_MOD_POOL = ["flip", "drift", "erratic", "blink", "decoy", "shrink"]


def make_level(n):
    boss = n % 5 == 0
    e = ENEMIES[(n // 5 - 1) % len(ENEMIES)] if boss else ENEMIES[(n - 1) % len(ENEMIES)]
    tier = (n - 1) // 6
    mods = list(e["mods"])
    if boss:
        for m in ("flip", _MOD_POOL[(n // 5) % len(_MOD_POOL)]):
            if m not in mods:
                mods.append(m)
    else:
        for j in range(min(tier, 3)):
            m = _MOD_POOL[(n + j) % len(_MOD_POOL)]
            if m not in mods:
                mods.append(m)
    hp = max(3, int(round(min(14, 3 + n // 2) * e["hp"])))
    if boss:
        hp = int(hp * 1.6) + 2
    return {
        "level": n, "boss": boss, "kind": e["kind"],
        "name": e["boss"] if boss else TIER_PREFIX[min(tier, 4)] + e["name"],
        "hue": ((0.55 + 0.13 * tier) % 1.0) if boss else (0.13 * tier) % 1.0,
        "mods": mods, "hp": hp,
        "speed": min(1.35, 0.55 + 0.04 * (n - 1)) * (1.05 if boss else 1.0),
        "zone": max(0.12, 0.34 - 0.007 * (n - 1) - (0.02 if boss else 0.0)),
        "gauge_time": max(3.4, 9.5 - 0.2 * (n - 1)) * (0.85 if boss else 1.0),
        "theme": ((n - 1) // 5) % 5,
    }


# --------------------------------------------------------------------------
#  SCENES
# --------------------------------------------------------------------------
K = pygame
KEYNAMES = {pygame.K_SPACE: "SPACE", pygame.K_ESCAPE: "ESC", pygame.K_RETURN: "ENTER"}


class Scene:
    overlay = False

    def __init__(self, app):
        self.app = app

    def handle(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, s):
        pass

    def on_blur(self):
        pass


class Overlay(Scene):
    """Modal panel: title, optional stars, text lines and key-driven options.
    options = [(keys, key_label, text, callback), ...]"""
    overlay = True

    def __init__(self, app, title, color, lines=(), options=(), stars=None):
        super().__init__(app)
        self.title, self.color, self.lines = title, color, list(lines)
        self.options, self.stars = list(options), stars
        self.t = 0.0
        self.shown = 0
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill(INK + (150,))

    def update(self, dt):
        self.t += dt
        if self.stars is not None:
            n = sum(1 for i in range(self.stars) if self.t > 0.3 + 0.25 * i)
            if n > self.shown:
                self.shown = n
                self.app.audio.play("perfect" if n == 3 else "good")

    def handle(self, e):
        if e.type == pygame.KEYDOWN and self.t > 0.25:
            for keys, _label, _text, fn in self.options:
                if e.key in keys:
                    self.app.audio.play("confirm")
                    fn()
                    return

    def draw(self, s):
        s.blit(self.shade, (0, 0))
        h = 32 + (28 if self.stars is not None else 0) + len(self.lines) * 11 + 8 + len(self.options) * 12 + 6
        w = 236
        x, y = (W - w) // 2, (H - h) // 2
        panel(s, (x, y, w, h))
        cy = y + 9
        draw_text(s, self.title, W // 2, cy, self.color, 2, "center")
        cy += 24
        if self.stars is not None:
            for i in range(3):
                sx = W // 2 - 31 + i * 22
                if i < self.stars and self.t > 0.3 + 0.25 * i:
                    k = self.t - (0.3 + 0.25 * i)
                    bump = -int(4 * max(0.0, 1 - k * 6)) if k < 0.17 else 0
                    s.blit(big_icon("star"), (sx, cy + bump))
                else:
                    s.blit(big_icon("star", empty=True), (sx, cy))
            cy += 28
        for text, col in self.lines:
            draw_text(s, text, W // 2, cy, col, 1, "center")
            cy += 11
        cy += 8
        for _keys, label, text, _fn in self.options:
            draw_text(s, f"[{label}] {text}", W // 2, cy, STEEL, 1, "center")
            cy += 12


def make_pause(app, restart):
    opts = [((pygame.K_p, pygame.K_ESCAPE, pygame.K_RETURN), "P", "RESUME", app.pop),
            ((pygame.K_r,), "R", "RESTART", restart),
            ((pygame.K_q,), "Q", "QUIT TO MENU", lambda: app.pop(2))]
    return Overlay(app, "PAUSED", WHITE, [("CATCH YOUR BREATH, HERO", STEEL)], opts)


# --------------------------------------------------------------------------
#  TITLE
# --------------------------------------------------------------------------
class TitleScene(Scene):
    ITEMS = ["CAMPAIGN", "SURVIVAL", "VERSUS 2P", "HOW TO PLAY", "SETTINGS", "QUIT"]

    def __init__(self, app):
        super().__init__(app)
        if WEB:
            self.ITEMS = self.ITEMS[:-1]      # nothing to quit to in a browser tab
        self.sel = 0
        self.t = 0.0
        self.theme = random.randrange(5)
        self.bg = get_bg(self.theme)
        self.amb = Ambient(self.theme)
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill(INK + (90,))

    def update(self, dt):
        self.t += dt
        self.amb.update(dt)

    def activate(self, i):
        a = self.app
        a.audio.play("confirm")
        if i == 0:
            a.push(LevelSelectScene(a))
        elif i == 1:
            a.push(BattleScene(a, "survival", 1))
        elif i == 2:
            a.push(VersusScene(a))
        elif i == 3:
            a.push(HowToScene(a))
        elif i == 4:
            a.push(SettingsScene(a))
        else:
            a.running = False

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        n = len(self.ITEMS)
        if e.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % n
            self.app.audio.play("select")
        elif e.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % n
            self.app.audio.play("select")
        elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.activate(self.sel)
        elif pygame.K_1 <= e.key <= pygame.K_6 and e.key - pygame.K_1 < n:
            self.sel = e.key - pygame.K_1
            self.activate(self.sel)
        elif e.key == pygame.K_ESCAPE and not WEB:
            self.app.running = False

    def draw(self, s):
        s.blit(self.bg, (0, 0))
        self.amb.draw(s, self.app.cfg["particles"])
        s.blit(self.shade, (0, 0))
        bob = int(round(math.sin(self.t * 2.2) * 2))
        draw_text(s, "TIMING", W // 2, 10 + bob, YELLOW, 5, "center", BROWN)
        draw_text(s, "CLASH", W // 2, 52 - bob, WHITE, 5, "center", RED)
        # the two rivals
        hb = 1 if math.sin(self.t * 5) > 0 else 0
        s.blit(pygame.transform.scale(hero_sprite(0), (32, 32)), (34, 98 - hb))
        draw_shadow(s, 50, 132, 30)
        slime = enemy_sprite("slime", 0.0)
        s.blit(pygame.transform.scale(slime, (32, 32)), (254, 98 + hb))
        draw_shadow(s, 270, 132, 30)
        # menu
        for i, item in enumerate(self.ITEMS):
            y = 92 + i * 12
            if i == self.sel:
                label = f"> {item} <" if int(self.t * 3) % 2 == 0 else f"  {item}  "
                draw_text(s, label, W // 2, y, YELLOW, 1, "center")
            else:
                draw_text(s, item, W // 2, y, WHITE, 1, "center")
        sv = self.app.save
        draw_text(s, f"LEVEL {sv.highest}", 6, 172, STEEL)
        draw_text(s, f"BEST WAVE {sv.survival_wave}", W - 6, 172, STEEL, 1, "right")
        draw_text(s, "ARROWS + ENTER", W // 2, 172, STEEL, 1, "center")


# --------------------------------------------------------------------------
#  LEVEL SELECT
# --------------------------------------------------------------------------
class LevelSelectScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.cur = app.save.highest
        self.t = 0.0
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill(INK + (175,))

    def update(self, dt):
        self.t += dt

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        hi = self.app.save.highest
        old = self.cur
        if e.key == pygame.K_LEFT:
            self.cur -= 1
        elif e.key == pygame.K_RIGHT:
            self.cur += 1
        elif e.key == pygame.K_UP:
            self.cur -= 5
        elif e.key == pygame.K_DOWN:
            self.cur += 5
        elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.app.audio.play("confirm")
            self.app.push(BattleScene(self.app, "campaign", self.cur))
            return
        elif e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.audio.play("back")
            self.app.pop()
            return
        self.cur = max(1, min(hi, self.cur))
        if self.cur != old:
            self.app.audio.play("select")

    def draw(self, s):
        sv = self.app.save
        self.cur = max(1, min(sv.highest, self.cur))
        cur_lv = make_level(self.cur)
        s.blit(get_bg(cur_lv["theme"]), (0, 0))
        s.blit(self.shade, (0, 0))
        draw_text(s, "SELECT LEVEL", W // 2, 5, YELLOW, 2, "center")
        draw_text(s, f"WORLD {cur_lv['theme'] + 1} - {WORLD_NAMES[cur_lv['theme']]}", W // 2, 24, STEEL, 1, "center")
        page = (self.cur - 1) // 10
        for i in range(10):
            n = page * 10 + i + 1
            col, row = i % 5, i // 5
            x, y = 5 + col * 63, 36 + row * 49
            lv = make_level(n)
            unlocked = n <= sv.highest
            selected = n == self.cur
            pygame.draw.rect(s, INK, (x, y, 58, 44))
            if selected:
                border = YELLOW if int(self.t * 4) % 2 == 0 else ORANGE
            elif lv["boss"]:
                border = RED
            else:
                border = STEEL if unlocked else CHAR
            pygame.draw.rect(s, border, (x + 1, y + 1, 56, 42))
            pygame.draw.rect(s, NAVY if unlocked else INK, (x + 2, y + 2, 54, 40))
            if unlocked:
                spr = enemy_sprite(lv["kind"], lv["hue"])
                s.blit(spr, (x + 21, y + 4))
                draw_text(s, str(n), x + 29, y + 22, WHITE if not lv["boss"] else RED, 1, "center")
                got = sv.star_count(n)
                for k in range(3):
                    s.blit(icon("star", empty=k >= got), (x + 14 + k * 10, y + 31))
            else:
                s.blit(icon("lock"), (x + 25, y + 10))
                draw_text(s, str(n), x + 29, y + 26, CHAR, 1, "center")
        panel(s, (5, 134, 310, 34))
        draw_text(s, f"LEVEL {self.cur}: {cur_lv['name']}", 12, 139, RED if cur_lv["boss"] else YELLOW)
        draw_text(s, f"HP {cur_lv['hp']}  SPEED {cur_lv['speed']:.2f}  ZONE {int(cur_lv['zone'] * 100)}%", 12, 149, WHITE)
        traits = ", ".join(MOD_TEXT[m] for m in cur_lv["mods"]) or "NO TRICKS - JUST TIMING"
        draw_text(s, traits, 12, 158, CYAN)
        draw_text(s, "ARROWS: PICK   ENTER: FIGHT   ESC: BACK", W // 2, 171, STEEL, 1, "center")


# --------------------------------------------------------------------------
#  HOW TO PLAY
# --------------------------------------------------------------------------
class HowToScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.page = 0
        self.t = 0.0
        self.bar = TimingBar(24, 34, 100, YELLOW)
        self.bar.configure(0.55, 0.3, [], 0.5)
        self.bar.zone_c = 0.5
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill(INK + (170,))

    def update(self, dt):
        self.t += dt
        self.bar.update(dt)
        self.bar.zone_c = 0.5

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.audio.play("back")
            self.app.pop()
        elif e.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE, pygame.K_RETURN):
            self.page = 1 - self.page
            self.app.audio.play("select")

    def draw(self, s):
        s.blit(get_bg(2), (0, 0))
        s.blit(self.shade, (0, 0))
        draw_text(s, "HOW TO PLAY", W // 2, 6, YELLOW, 2, "center")
        if self.page == 0:
            b = self.bar
            b.draw(s)
            zc = b.top + int(b.zone_c * b.h)
            for label, y, col in (("PERFECT 2X", zc, YELLOW), ("GOOD 1X", zc - int(b.zone * b.h * 0.42), GREEN),
                                  ("MISS", zc + int(b.zone * b.h) + 6, RED)):
                pygame.draw.rect(s, col, (b.x + 26, y, 10, 1))
                draw_text(s, label, b.x + 40, y - 3, col)
            lines = [
                ("1. WATCH THE LINE BOUNCE", WHITE), ("2. HIT SPACE IN THE GREEN", WHITE),
                ("   GOLD CENTRE = PERFECT", YELLOW), ("3. HITS HURT THE ENEMY", WHITE),
                ("4. MISSES FILL ITS RAGE", WHITE), ("   FULL RAGE = LOSE A HEART", RED),
                ("5. 5 HIT STREAK = POWER", WHITE), ("   STRIKE AND HEAL", CYAN),
                ("", WHITE), ("P1: SPACE / A / CLICK", BLUE), ("P2: L", RED),
                ("P PAUSE  F11 SCREEN  M MUTE", STEEL),
            ]
            for i, (t, c) in enumerate(lines):
                draw_text(s, t, 148, 32 + i * 11, c)
        else:
            draw_text(s, "EVERY ENEMY HAS A TRICK", W // 2, 26, WHITE, 1, "center")
            for i, e in enumerate(ENEMIES):
                col, row = i % 2, i // 2
                x, y = 16 + col * 156, 42 + row * 38
                panel(s, (x, y - 4, 148, 34))
                bob = 1 if math.sin(self.t * 5 + i) > 0 else 0
                s.blit(enemy_sprite(e["kind"]), (x + 6, y - bob))
                draw_text(s, e["name"], x + 28, y + 1, YELLOW)
                trait = MOD_TEXT[e["mods"][0]] if e["mods"] else "NO TRICKS"
                draw_text(s, trait, x + 28, y + 12, CYAN)
            draw_text(s, "EVERY 5TH LEVEL IS A BOSS WITH EXTRA TRICKS", W // 2, 158, RED, 1, "center")
        draw_text(s, f"< PAGE {self.page + 1}/2 >   ESC: BACK", W // 2, 171, STEEL, 1, "center")


# --------------------------------------------------------------------------
#  SETTINGS
# --------------------------------------------------------------------------
class SettingsScene(Scene):
    ITEMS = [
        ("difficulty", "DIFFICULTY", [0, 1, 2], lambda v: DIFFICULTY[v]["name"],
         "HEARTS, LOCK TIME AND ENEMY RAGE SPEED"),
        ("music", "MUSIC", [False, True], None, "CHIPTUNE BACKGROUND LOOP"),
        ("sfx", "SOUND FX", [False, True], None, "HITS, MISSES AND JINGLES"),
        ("shake", "SCREEN SHAKE", [False, True], None, "CAMERA KICK ON IMPACTS"),
        ("particles", "PARTICLES", [False, True], None, "SPARKS, EMBERS AND DUST"),
        ("show_fps", "FPS COUNTER", [False, True], None, "SHOW FRAMES PER SECOND"),
        ("vs_rounds", "VERSUS MATCH", [1, 3, 5], lambda v: f"BEST OF {v}", "ROUNDS NEEDED IN 2 PLAYER MODE"),
        ("fullscreen", "FULLSCREEN", [False, True], None, "ALSO F11 ANYWHERE"),
        ("reset", "RESET PROGRESS", None, None, "ERASE LEVELS, STARS AND HIGH SCORES"),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.items = [it for it in self.ITEMS if not (WEB and it[0] == "fullscreen")]
        self.sel = 0
        self.confirm = False
        self.t = 0.0
        self.shade = pygame.Surface((W, H), pygame.SRCALPHA)
        self.shade.fill(INK + (170,))

    def update(self, dt):
        self.t += dt

    def change(self, d):
        key, _label, values, _fmt, _desc = self.items[self.sel]
        a = self.app
        if key == "reset":
            if d > 0 or d == 0:
                if self.confirm:
                    a.save.reset()
                    self.confirm = False
                    a.audio.play("ko")
                else:
                    self.confirm = True
                    a.audio.play("select")
            return
        cur = a.cfg[key]
        idx = values.index(cur) if cur in values else 0
        a.cfg[key] = values[(idx + (d or 1)) % len(values)]
        if key == "music":
            a.audio.set_music(a.cfg["music"])
        elif key == "fullscreen":
            a.set_fullscreen(a.cfg["fullscreen"])
        a.save.save()
        a.audio.play("select")

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        n = len(self.items)
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.audio.play("back")
            self.app.pop()
        elif e.key in (pygame.K_UP, pygame.K_w):
            self.sel = (self.sel - 1) % n
            self.confirm = False
            self.app.audio.play("select")
        elif e.key in (pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + 1) % n
            self.confirm = False
            self.app.audio.play("select")
        elif e.key in (pygame.K_LEFT, pygame.K_a):
            self.change(-1)
        elif e.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_RETURN, pygame.K_SPACE):
            self.change(1)

    def draw(self, s):
        s.blit(get_bg(1), (0, 0))
        s.blit(self.shade, (0, 0))
        draw_text(s, "SETTINGS", W // 2, 6, YELLOW, 2, "center")
        for i, (key, label, _values, fmt, _desc) in enumerate(self.items):
            y = 28 + i * 14
            sel = i == self.sel
            if sel:
                pygame.draw.rect(s, NAVY, (30, y - 3, 260, 12))
                pygame.draw.rect(s, STEEL, (30, y - 3, 260, 12), 1)
            draw_text(s, label, 40, y, YELLOW if sel else WHITE)
            if key == "reset":
                txt = "PRESS AGAIN TO CONFIRM" if (sel and self.confirm) else "[ ERASE ]"
                col = RED
            else:
                v = self.app.cfg[key]
                txt = fmt(v) if fmt else ("ON" if v else "OFF")
                col = (GREEN if v else RED) if fmt is None else CYAN
            draw_text(s, f"< {txt} >" if sel and key != "reset" else txt, 280, y, col, 1, "right")
        draw_text(s, self.items[self.sel][4], W // 2, 156, STEEL, 1, "center")
        draw_text(s, "UP/DOWN: SELECT  LEFT/RIGHT: CHANGE  ESC: BACK", W // 2, 171, STEEL, 1, "center")


# --------------------------------------------------------------------------
#  BATTLE  (campaign + survival)
# --------------------------------------------------------------------------
class BattleScene(Scene):
    HERO_X = 60
    ENEMY_CX = 244
    INTRO_T = 1.9
    ATK_T = 0.55

    def __init__(self, app, mode="campaign", level=1):
        super().__init__(app)
        self.mode, self.level = mode, level
        self.diff = DIFFICULTY[app.cfg["difficulty"]]
        self.max_hearts = self.diff["hearts"]
        self.hearts = self.max_hearts
        self.score = 0
        self.fx = FX(app)
        self.bar = TimingBar(W // 2 - 8)
        self.hitstop = 0.0
        self.hero_atk = self.hero_hurt = self.en_hurt = self.en_atk = 0.0
        self.en_hit_done = True
        self.clock_t = 0.0
        self.tutorial = mode == "campaign" and level == 1
        self.dim = pygame.Surface((W, 64), pygame.SRCALPHA)
        self.dim.fill(INK + (175,))
        self.setup_enemy()

    # ---- setup -----------------------------------------------------------
    def setup_enemy(self):
        lv = make_level(self.level)
        self.lv = lv
        self.hp = self.hp_max = lv["hp"]
        self.bar.configure(lv["speed"], lv["zone"], lv["mods"], self.diff["lock"])
        self.gauge = 0.0
        self.gauge_time = lv["gauge_time"] * self.diff["gauge"]
        self.scale = 2 if lv["boss"] else 1
        self.sprite = enemy_sprite(lv["kind"], lv["hue"], self.scale)
        self.bg = get_bg(lv["theme"])
        self.amb = Ambient(lv["theme"])
        self.phase, self.t = "intro", 0.0
        self.go_played = False
        self.combo = 0
        self.stat = {"perfect": 0, "good": 0, "miss": 0, "lost": 0, "maxcombo": 0}
        self.en_atk = 0.0
        self.en_hit_done = True

    def enemy_center(self):
        return self.ENEMY_CX, GROUND - 8 * self.scale

    # ---- input -----------------------------------------------------------
    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_SPACE, pygame.K_a):
                self.strike()
            elif e.key in (pygame.K_p, pygame.K_ESCAPE):
                self.pause()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.strike()

    def on_blur(self):
        self.pause()

    def pause(self):
        if self.phase in ("intro", "play"):
            self.app.audio.play("select")
            self.app.push(make_pause(self.app, self.restart))

    def restart(self):
        a = self.app
        a.pop(2)
        a.push(BattleScene(a, self.mode, 1 if self.mode == "survival" else self.level))

    # ---- combat ----------------------------------------------------------
    def strike(self):
        if self.phase == "intro":
            if self.t > 0.5:
                self.t = self.INTRO_T
            return
        if self.phase != "play":
            return
        r = self.bar.press()
        a = self.app
        if r is None:
            a.audio.play("locked")
            return
        bx = self.bar.x + 8
        if r in ("good", "perfect"):
            perfect = r == "perfect"
            self.combo += 1
            self.stat["perfect" if perfect else "good"] += 1
            self.stat["maxcombo"] = max(self.stat["maxcombo"], self.combo)
            dmg = 2 if perfect else 1
            power = self.combo % 5 == 0
            if power:
                dmg += 1
            self.score += (150 if perfect else 100) + 10 * self.combo
            self.hero_atk = 0.2
            ex, ey = self.enemy_center()
            self.fx.shot(self.HERO_X + 14, GROUND - 10, ex - 6 * self.scale, ey, 520,
                         YELLOW if perfect else CYAN, lambda: self.impact(dmg, perfect, power))
            self.fx.text("PERFECT!" if perfect else "GOOD", bx, self.bar.cursor_y() - 6,
                         YELLOW if perfect else GREEN)
            a.audio.play("perfect" if perfect else "good")
            self.tutorial = False
        else:
            self.combo = 0
            self.stat["miss"] += 1
            self.gauge = min(1.0, self.gauge + 0.22)
            a.audio.play("miss")
            a.shake(2, 0.12)
            self.fx.text("TRAP!" if r == "decoy" else "MISS", bx, self.bar.cursor_y() - 6, RED)
            self.fx.burst(bx, self.bar.cursor_y(), RED, 6, 50, 0.3)
            if r == "decoy":
                self.hurt_hero()

    def impact(self, dmg, perfect, power):
        if self.phase != "play":
            return
        a = self.app
        ex, ey = self.enemy_center()
        self.hp = max(0, self.hp - dmg)
        self.en_hurt = 0.3
        self.gauge = max(0.0, self.gauge - (0.30 if perfect else 0.18))
        self.hitstop = 0.09 if perfect else 0.05
        self.fx.burst(ex, ey, YELLOW if perfect else CYAN, 8 + 4 * dmg, 110)
        self.fx.text(f"-{dmg}", ex, ey - 10 * self.scale - 8, WHITE, 2)
        a.shake(1 + dmg, 0.16)
        a.audio.play("thud")
        if power:
            self.fx.text("POWER STRIKE!", W // 2, 22, ORANGE, 1, 1.1)
            a.audio.play("power")
            a.flash_screen(WHITE, 70, 0.15)
            self.heal()
        if self.hp <= 0:
            self.begin_win()

    def heal(self):
        if self.hearts < self.max_hearts:
            self.hearts += 1
            self.fx.text("+1", self.HERO_X + 8, GROUND - 30, GREEN, 2)
            self.app.audio.play("heal")

    def hurt_hero(self):
        if self.phase != "play":
            return
        self.hearts -= 1
        self.stat["lost"] += 1
        self.combo = 0
        self.hero_hurt = 0.5
        self.gauge = 0.12
        hx = self.HERO_X + 8
        self.fx.burst(hx, GROUND - 8, RED, 14, 100)
        self.fx.text("-1", hx, GROUND - 32, RED, 2)
        self.app.audio.play("hurt")
        self.app.shake(5, 0.3)
        self.app.flash_screen(RED, 100, 0.22)
        if self.hearts <= 0:
            self.begin_lose()

    def begin_win(self):
        self.phase, self.t = "win", -0.1
        ex, ey = self.enemy_center()
        self.fx.burst(ex, ey, WHITE, 30, 160, 0.8)
        self.fx.burst(ex, ey, YELLOW, 20, 120, 0.8)
        self.app.audio.play("ko")
        self.app.shake(6, 0.35)

    def begin_lose(self):
        self.phase, self.t = "lose", 0.0
        self.en_atk = 0.0
        self.app.audio.play("lose")

    def finish_win(self):
        a = self.app
        if self.mode == "campaign":
            lost = self.stat["lost"]
            stars = 3 if lost == 0 else (2 if lost <= 2 else 1)
            self.score += 500 + self.hearts * 100 + stars * 200
            a.save.record_level(self.level, stars)
            lines = [(f"SCORE {self.score}", WHITE), (f"BEST COMBO {self.stat['maxcombo']}", CYAN),
                     (f"HEARTS LOST {lost}", GREEN if lost == 0 else RED),
                     (f"LEVEL {self.level + 1} UNLOCKED", YELLOW)]
            opts = [((pygame.K_SPACE, pygame.K_RETURN), "SPACE", "NEXT LEVEL", lambda: self.go_level(self.level + 1)),
                    ((pygame.K_r,), "R", "RETRY", lambda: self.go_level(self.level)),
                    ((pygame.K_ESCAPE,), "ESC", "LEVEL SELECT", lambda: a.pop(2))]
            self.phase = "done"
            a.audio.play("win")
            a.push(Overlay(a, "BOSS DOWN!" if self.lv["boss"] else "LEVEL CLEAR!", GREEN, lines, opts, stars))
        else:
            self.score += 300 + self.level * 40 + (150 if self.stat["lost"] == 0 else 0)
            self.level += 1
            a.save.survival_wave = max(a.save.survival_wave, self.level - 1)
            self.fx.text("WAVE CLEAR!", W // 2, 70, GREEN, 2, 1.2)
            self.heal()
            self.setup_enemy()
            self.t = -0.4

    def finish_lose(self):
        a = self.app
        self.phase = "done"
        if self.mode == "campaign":
            lines = [(f"ENEMY HP LEFT {self.hp}/{self.hp_max}", WHITE), (f"SCORE {self.score}", STEEL)]
            opts = [((pygame.K_SPACE, pygame.K_RETURN, pygame.K_r), "SPACE", "TRY AGAIN", lambda: self.go_level(self.level)),
                    ((pygame.K_ESCAPE,), "ESC", "LEVEL SELECT", lambda: a.pop(2))]
            a.push(Overlay(a, "DEFEATED", RED, lines, opts))
        else:
            sv = a.save
            new_best = self.score > sv.survival_best
            sv.survival_best = max(sv.survival_best, self.score)
            sv.survival_wave = max(sv.survival_wave, self.level)
            sv.save()
            lines = [(f"REACHED WAVE {self.level}", WHITE), (f"SCORE {self.score}", YELLOW),
                     ("NEW HIGH SCORE!" if new_best else f"BEST {sv.survival_best}", GREEN if new_best else STEEL)]
            opts = [((pygame.K_SPACE, pygame.K_RETURN, pygame.K_r), "SPACE", "RUN AGAIN", self.restart),
                    ((pygame.K_ESCAPE,), "ESC", "MENU", lambda: a.pop(2))]
            a.push(Overlay(a, "GAME OVER", RED, lines, opts))

    def go_level(self, n):
        a = self.app
        a.pop(2)
        a.push(BattleScene(a, "campaign", n))

    # ---- update ----------------------------------------------------------
    def update(self, dt):
        if self.hitstop > 0:
            self.hitstop -= dt
            dt = 0.0
        self.clock_t += dt
        self.fx.update(dt)
        self.amb.update(dt)
        self.hero_atk = max(0.0, self.hero_atk - dt)
        self.hero_hurt = max(0.0, self.hero_hurt - dt)
        self.en_hurt = max(0.0, self.en_hurt - dt)
        if self.phase == "intro":
            self.t += dt
            if not self.go_played and self.t > 1.1:
                self.go_played = True
                self.app.audio.play("go")
            if self.t >= self.INTRO_T:
                self.phase = "play"
        elif self.phase == "play":
            self.bar.update(dt)
            if self.en_atk > 0:
                self.en_atk -= dt
                if not self.en_hit_done and self.en_atk <= 0.25:
                    self.en_hit_done = True
                    self.hurt_hero()
            else:
                self.gauge += dt / self.gauge_time
                if self.gauge >= 1.0:
                    self.gauge = 1.0
                    self.en_atk = self.ATK_T
                    self.en_hit_done = False
                    self.app.audio.play("rage")
        elif self.phase == "win":
            self.t += dt
            if 0 < self.t < 0.7 and random.random() < 0.3:
                ex, ey = self.enemy_center()
                self.fx.burst(ex + random.randint(-8, 8) * self.scale, ey + random.randint(-8, 8) * self.scale,
                              random.choice((WHITE, YELLOW, ORANGE)), 6, 90)
            if self.t >= 1.3:
                self.finish_win()
        elif self.phase == "lose":
            self.t += dt
            if self.t >= 1.7:
                self.finish_lose()

    # ---- drawing ---------------------------------------------------------
    def draw_hero(self, s):
        x = self.HERO_X
        if self.hero_atk > 0:
            x += int(10 * math.sin(math.pi * (1 - self.hero_atk / 0.2)))
        if self.hero_hurt > 0:
            x -= int(4 * math.sin(math.pi * (1 - self.hero_hurt / 0.5)))
        draw_shadow(s, x + 8, GROUND, 18)
        spr = hero_sprite(0)
        if self.phase == "lose" and self.t > 0.2:
            img = pygame.transform.rotate(spr, -90)
            blit_char(s, img, x, GROUND)
            return
        flash = WHITE if self.hero_hurt > 0 and int(self.hero_hurt * 30) % 2 == 0 else None
        bob = 1 if math.sin(self.clock_t * 5) > 0 else 0
        blit_char(s, spr, x, GROUND - bob, flash)

    def draw_enemy(self, s):
        sz = 16 * self.scale
        left = self.ENEMY_CX - sz // 2
        feet = GROUND
        kind = self.lv["kind"]
        alpha = 255
        if self.phase == "intro":
            left += int(max(0.0, 1 - self.t / 0.7) ** 2 * 90)
        if self.en_atk > 0:
            p = 1 - self.en_atk / self.ATK_T
            left -= int(48 * math.sin(math.pi * min(1.0, p)))
        if self.en_hurt > 0:
            left += int(math.sin(self.clock_t * 70) * 2)
        if kind in ("bat", "ghost"):
            feet -= 8 * self.scale // 2 + int(2 * math.sin(self.clock_t * 3))
        else:
            feet -= 1 if math.sin(self.clock_t * 4) > 0 else 0
        draw_shadow(s, self.ENEMY_CX, GROUND, sz + 4)
        if kind == "ghost":
            alpha = 215
        flash = None
        if self.en_hurt > 0.18:
            flash = WHITE
        elif self.phase == "play" and self.gauge > 0.8 and int(self.clock_t * 10) % 4 == 0:
            flash = RED
        if self.phase == "win":
            if self.t > 0.9:
                return
            if self.t > 0 and int(self.t * 25) % 2 == 0:
                return
            flash = WHITE
        blit_char(s, self.sprite, left, feet, flash, alpha)

    def draw_hud(self, s):
        for i in range(self.max_hearts):
            s.blit(icon("heart", empty=i >= self.hearts), (6 + i * 10, 4))
        draw_text(s, f"{self.score:07d}", 7, 16, YELLOW)
        label = f"WAVE {self.level}" if self.mode == "survival" else f"LEVEL {self.level}"
        draw_text(s, label, W // 2, 4, WHITE, 1, "center")
        draw_text(s, self.lv["name"], W - 6, 4, RED if self.lv["boss"] else WHITE, 1, "right")
        bar_gauge(s, W - 6 - 110, 14, 110, 7, self.hp / self.hp_max, RED, WINE, ORANGE)
        for i in range(1, self.hp_max):
            x = W - 6 - 110 + (110 * i) // self.hp_max
            pygame.draw.rect(s, INK, (x, 14, 1, 7))
        if self.combo >= 2:
            draw_text(s, f"COMBO x{self.combo}", W // 2, 15, ORANGE if self.combo >= 5 else WHITE, 1, "center")
        # rage meter below the enemy, key hint below the hero
        ex = self.ENEMY_CX
        hot = self.gauge > 0.8 and int(self.clock_t * 8) % 2 == 0
        bar_gauge(s, ex - 22, 160, 44, 5, self.gauge, RED if hot else ORANGE, CHAR, YELLOW)
        draw_text(s, "RAGE", ex, 167, RED if hot else STEEL, 1, "center")
        keycap(s, "SPACE", self.HERO_X + 8, 158)

    def draw_banner(self, s):
        if self.phase == "intro":
            if self.t < 1.1:
                s.blit(self.dim, (0, 50))
                lv = self.lv
                draw_text(s, WORLD_NAMES[lv["theme"]], W // 2, 55, STEEL, 1, "center")
                head = ("WAVE %d" if self.mode == "survival" else "LEVEL %d") % self.level
                draw_text(s, head, W // 2, 65, YELLOW, 3, "center")
                draw_text(s, ("BOSS: " if lv["boss"] else "") + lv["name"], W // 2, 92, RED if lv["boss"] else WHITE, 1, "center")
                trait = ", ".join(MOD_TEXT[m] for m in lv["mods"]) or "NO TRICKS"
                draw_text(s, trait, W // 2, 104, CYAN, 1, "center")
            elif int(self.t * 10) % 2 == 0 or self.t > 1.5:
                draw_text(s, "FIGHT!", W // 2, 68, ORANGE, 4, "center", INK)
        elif self.phase == "play" and self.tutorial and self.stat["perfect"] + self.stat["good"] == 0:
            if int(self.clock_t * 2) % 2 == 0:
                draw_text(s, "PRESS SPACE WHEN THE LINE IS IN THE GREEN ZONE", W // 2, 140, WHITE, 1, "center")
        elif self.phase == "win" and self.t > 0.5:
            draw_text(s, "VICTORY!", W // 2, 68, YELLOW, 3, "center")
        elif self.phase == "lose" and self.t > 0.5:
            draw_text(s, "DEFEATED", W // 2, 68, RED, 3, "center")

    def draw(self, s):
        s.blit(self.bg, (0, 0))
        self.amb.draw(s, self.app.cfg["particles"])
        self.bar.draw(s)
        self.draw_enemy(s)
        self.draw_hero(s)
        self.fx.draw(s)
        self.draw_hud(s)
        self.draw_banner(s)


# --------------------------------------------------------------------------
#  VERSUS  (local 2-player duel)
# --------------------------------------------------------------------------
class VersusScene(Scene):
    BAR_X = (100, 204)
    HERO_X = (28, 276)
    MAX_HP = 10
    ROUND_MODS = [[], ["flip"], ["drift"], ["erratic"], ["blink"]]

    def __init__(self, app):
        super().__init__(app)
        self.need = app.cfg["vs_rounds"] // 2 + 1
        self.wins = [0, 0]
        self.round = 1
        self.fx = FX(app)
        self.keys = (pygame.K_a, pygame.K_l)
        self.clock_t = 0.0
        self.start_round()

    def start_round(self):
        self.hp = [self.MAX_HP, self.MAX_HP]
        self.combo = [0, 0]
        self.bars = [TimingBar(self.BAR_X[0], color=BLUE), TimingBar(self.BAR_X[1], color=RED)]
        mods = self.ROUND_MODS[(self.round - 1) % len(self.ROUND_MODS)]
        for b in self.bars:
            b.configure(0.8, 0.28, mods, 0.8)
        self.mods = mods
        self.phase, self.t = "intro", 3.0
        self.count_shown = 4
        self.fight_t = 0.0
        self.elapsed, self.rage = 0.0, 0
        self.hurt = [0.0, 0.0]
        self.atk = [0.0, 0.0]
        self.theme = (self.round - 1) % 5
        self.bg = get_bg(self.theme)
        self.amb = Ambient(self.theme)

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        if e.key == self.keys[0]:
            self.press(0)
        elif e.key == self.keys[1]:
            self.press(1)
        elif e.key in (pygame.K_p, pygame.K_ESCAPE):
            self.pause()

    def on_blur(self):
        self.pause()

    def pause(self):
        if self.phase in ("intro", "play"):
            self.app.push(make_pause(self.app, self.restart))

    def restart(self):
        a = self.app
        a.pop(2)
        a.push(VersusScene(a))

    def press(self, i):
        if self.phase != "play":
            return
        b = self.bars[i]
        r = b.press()
        a = self.app
        bx = b.x + 8
        if r is None:
            a.audio.play("locked")
        elif r in ("good", "perfect"):
            perfect = r == "perfect"
            self.combo[i] += 1
            dmg = 2 if perfect else 1
            power = self.combo[i] % 5 == 0
            if power:
                dmg += 1
            self.atk[i] = 0.2
            sx = self.HERO_X[i] + (14 if i == 0 else 2)
            tx = self.HERO_X[1 - i] + (4 if i == 0 else 12)
            self.fx.shot(sx, GROUND - 10, tx, GROUND - 10, 560, YELLOW if perfect else (CYAN if i == 0 else ORANGE),
                         lambda: self.deal(i, dmg, perfect, power))
            self.fx.text("PERFECT!" if perfect else "GOOD", bx, b.cursor_y() - 6, YELLOW if perfect else GREEN)
            a.audio.play("perfect" if perfect else "good")
        else:
            self.combo[i] = 0
            self.fx.text("MISS", bx, b.cursor_y() - 6, RED)
            a.audio.play("miss")
            a.shake(2, 0.1)

    def deal(self, i, dmg, perfect, power):
        if self.phase != "play":
            return
        a = self.app
        v = 1 - i
        self.hp[v] = max(0, self.hp[v] - dmg)
        self.hurt[v] = 0.4
        vx = self.HERO_X[v] + 8
        self.fx.burst(vx, GROUND - 8, YELLOW if perfect else (BLUE if i == 0 else RED), 8 + 4 * dmg, 110)
        self.fx.text(f"-{dmg}", vx, GROUND - 32, WHITE, 2)
        a.shake(1 + dmg, 0.15)
        a.audio.play("thud")
        if power:
            self.fx.text("POWER STRIKE!", self.BAR_X[i] + 8, 22, ORANGE)
            a.audio.play("power")
            if self.hp[i] < self.MAX_HP:
                self.hp[i] += 1
        if self.hp[v] <= 0:
            self.phase, self.t = "ko", 0.0
            self.winner = i
            self.wins[i] += 1
            self.fx.burst(vx, GROUND - 8, WHITE, 30, 150, 0.8)
            a.audio.play("ko")
            a.shake(6, 0.4)
            a.flash_screen(WHITE, 90, 0.2)

    def update(self, dt):
        self.clock_t += dt
        self.fx.update(dt)
        self.amb.update(dt)
        for i in (0, 1):
            self.hurt[i] = max(0.0, self.hurt[i] - dt)
            self.atk[i] = max(0.0, self.atk[i] - dt)
        self.fight_t = max(0.0, self.fight_t - dt)
        if self.phase == "intro":
            self.t -= dt
            n = max(0, math.ceil(self.t))
            if n != self.count_shown and n > 0:
                self.count_shown = n
                self.app.audio.play("tick")
            if self.t <= 0:
                self.phase = "play"
                self.fight_t = 0.8
                self.app.audio.play("go")
        elif self.phase == "play":
            for b in self.bars:
                b.update(dt)
            self.elapsed += dt
            lv = int(self.elapsed / 8)
            if lv > self.rage:
                self.rage = lv
                for b in self.bars:
                    b.scale = min(1.6, 1 + 0.1 * lv)
                self.fx.text("RAGE UP!", W // 2, 90, RED, 2, 1.0)
                self.app.audio.play("rage")
        elif self.phase == "ko":
            self.t += dt
            if self.t >= 2.0:
                if max(self.wins) >= self.need:
                    self.finish_match()
                else:
                    self.round += 1
                    self.start_round()

    def finish_match(self):
        a = self.app
        self.phase = "done"
        w = 0 if self.wins[0] > self.wins[1] else 1
        lines = [(f"FINAL SCORE  {self.wins[0]} - {self.wins[1]}", WHITE)]
        opts = [((pygame.K_SPACE, pygame.K_RETURN, pygame.K_r), "SPACE", "REMATCH", self.restart),
                ((pygame.K_ESCAPE,), "ESC", "MENU", lambda: a.pop(2))]
        a.audio.play("win")
        a.push(Overlay(a, f"P{w + 1} WINS!", BLUE if w == 0 else RED, lines, opts))

    # ---- drawing ---------------------------------------------------------
    def draw_fighter(self, s, i):
        spr = hero_sprite(i)
        x = self.HERO_X[i]
        d = 1 if i == 0 else -1
        if self.atk[i] > 0:
            x += d * int(10 * math.sin(math.pi * (1 - self.atk[i] / 0.2)))
        if self.hurt[i] > 0:
            x -= d * int(4 * math.sin(math.pi * (1 - self.hurt[i] / 0.4)))
        draw_shadow(s, x + 8, GROUND, 18)
        if self.phase in ("ko", "done") and self.hp[i] <= 0:
            blit_char(s, pygame.transform.rotate(spr, -90 * d), x, GROUND)
            return
        flash = WHITE if self.hurt[i] > 0 and int(self.hurt[i] * 30) % 2 == 0 else None
        bob = 1 if math.sin(self.clock_t * 5 + i) > 0 else 0
        blit_char(s, spr, x, GROUND - bob, flash)

    def draw_hud(self, s):
        for i in (0, 1):
            col = BLUE if i == 0 else RED
            x = 8 if i == 0 else W - 8 - 104
            pygame.draw.rect(s, INK, (x - 1, 8, 106, 9))
            pygame.draw.rect(s, CHAR, (x, 9, 104, 7))
            fw = int(104 * self.hp[i] / self.MAX_HP)
            if fw > 0:
                fx0 = x if i == 0 else x + 104 - fw
                pygame.draw.rect(s, col, (fx0, 9, fw, 7))
                pygame.draw.rect(s, WHITE, (fx0, 9, fw, 1))
            for k in range(1, self.MAX_HP):
                pygame.draw.rect(s, INK, (x + 104 * k // self.MAX_HP, 9, 1, 7))
            draw_text(s, f"P{i + 1}", x if i == 0 else x + 104, 19, col, 1, "left" if i == 0 else "right")
            for k in range(self.need):
                px = (x + 18 + k * 8) if i == 0 else (x + 104 - 18 - k * 8 - 5)
                pygame.draw.rect(s, INK, (px - 1, 19, 7, 7))
                pygame.draw.rect(s, YELLOW if k < self.wins[i] else CHAR, (px, 20, 5, 5))
        draw_text(s, f"ROUND {self.round}", W // 2, 8, WHITE, 1, "center")
        draw_text(s, f"BEST OF {self.need * 2 - 1}", W // 2, 17, STEEL, 1, "center")
        if self.rage and int(self.clock_t * 4) % 2 == 0:
            draw_text(s, f"RAGE x{self.rage}", W // 2, 26, RED, 1, "center")
        for i in (0, 1):
            cx = self.BAR_X[i] + 8
            keycap(s, "A" if i == 0 else "L", cx, 138, BLUE if i == 0 else RED)
            if self.combo[i] >= 2:
                draw_text(s, f"COMBO x{self.combo[i]}", cx, 152, ORANGE if self.combo[i] >= 5 else WHITE, 1, "center")
        if self.mods:
            draw_text(s, MOD_TEXT[self.mods[0]], W // 2, 160, CYAN, 1, "center")

    def draw(self, s):
        s.blit(self.bg, (0, 0))
        self.amb.draw(s, self.app.cfg["particles"])
        for b in self.bars:
            b.draw(s)
        draw_text(s, "VS", W // 2, 66, YELLOW, 3, "center")
        self.draw_fighter(s, 0)
        self.draw_fighter(s, 1)
        self.fx.draw(s)
        self.draw_hud(s)
        if self.phase == "intro":
            n = max(1, math.ceil(self.t))
            draw_text(s, str(n), W // 2, 94, ORANGE, 5, "center")
        elif self.fight_t > 0:
            draw_text(s, "FIGHT!", W // 2, 94, ORANGE, 3, "center")
        elif self.phase == "ko" and self.t > 0.4:
            draw_text(s, f"P{self.winner + 1} WINS THE ROUND!", W // 2, 94, YELLOW, 1, "center")
            draw_text(s, "K.O.!", W // 2, 106, RED, 3, "center")


# --------------------------------------------------------------------------
#  APP
# --------------------------------------------------------------------------
class App:
    def __init__(self):
        pygame.mixer.pre_init(RATE, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Timing Clash")
        self.save = SaveData()
        self.cfg = self.save.settings
        self.fullscreen = False
        self.set_fullscreen(self.cfg["fullscreen"])
        try:
            pygame.display.set_icon(pygame.transform.scale(hero_sprite(0), (32, 32)))
        except Exception:
            pass
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.audio = Audio(self)
        self.scenes = []
        self.running = True
        self.blur_event = getattr(pygame, "WINDOWFOCUSLOST", None)
        self.shake_t = self.shake_mag = 0.0
        self.flash = None
        self.flash_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        self.push(TitleScene(self))

    # ---- scene stack -----------------------------------------------------
    def push(self, scene):
        self.scenes.append(scene)

    def pop(self, n=1):
        for _ in range(n):
            if self.scenes:
                self.scenes.pop()

    # ---- window / effects ------------------------------------------------
    def set_fullscreen(self, on):
        if WEB:    # the page handles fullscreen; the canvas is a fixed 4x surface
            self.fullscreen = False
            self.cfg["fullscreen"] = False
            if getattr(self, "win", None) is None:
                self.win = pygame.display.set_mode((W * 4, H * 4))
            return
        self.fullscreen = bool(on)
        self.cfg["fullscreen"] = self.fullscreen
        try:
            if self.fullscreen:
                self.win = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.win = pygame.display.set_mode((W * 4, H * 4), pygame.RESIZABLE)
        except pygame.error:
            self.fullscreen = False
            self.cfg["fullscreen"] = False
            self.win = pygame.display.set_mode((W * 4, H * 4), pygame.RESIZABLE)

    def shake(self, mag, dur):
        if self.cfg["shake"]:
            self.shake_mag = max(self.shake_mag, mag)
            self.shake_t = max(self.shake_t, dur)

    def flash_screen(self, color, alpha, dur):
        if self.cfg["shake"]:
            self.flash = [color, alpha, dur, dur]

    def present(self):
        win = pygame.display.get_surface() or self.win
        ww, wh = win.get_size()
        sc = min(ww // W, wh // H)
        if sc >= 1:
            img = pygame.transform.scale(self.canvas, (W * sc, H * sc))
        else:
            f = min(ww / W, wh / H)
            img = pygame.transform.scale(self.canvas, (max(1, int(W * f)), max(1, int(H * f))))
            sc = 1
        ox, oy = (ww - img.get_width()) // 2, (wh - img.get_height()) // 2
        if self.shake_t > 0:
            m = int(self.shake_mag)
            ox += random.randint(-m, m) * sc
            oy += random.randint(-m, m) * sc
        win.fill(INK)
        win.blit(img, (ox, oy))
        pygame.display.flip()

    # ---- main loop -------------------------------------------------------
    def frame(self):
        """Run one iteration of the game loop.  Returns False when the game is over."""
        dt = min(self.clock.tick(0 if WEB else FPS) / 1000.0, 1 / 30)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                if not WEB:
                    self.set_fullscreen(not self.fullscreen)
                    self.save.save()
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_m:
                self.audio.toggle_mute()
            elif self.blur_event is not None and e.type == self.blur_event:
                if self.scenes:
                    self.scenes[-1].on_blur()
            elif self.scenes:
                self.scenes[-1].handle(e)
        if not self.scenes or not self.running:
            return False
        self.audio.pump()
        self.scenes[-1].update(dt)
        if self.shake_t > 0:
            self.shake_t -= dt
            if self.shake_t <= 0:
                self.shake_mag = 0.0
        # draw: from the last non-overlay scene up to the top
        base = len(self.scenes) - 1
        while base > 0 and self.scenes[base].overlay:
            base -= 1
        for sc in self.scenes[base:]:
            sc.draw(self.canvas)
        if self.flash:
            self.flash[3] -= dt
            if self.flash[3] <= 0:
                self.flash = None
            else:
                a = int(self.flash[1] * self.flash[3] / self.flash[2])
                self.flash_surf.fill(self.flash[0] + (a,))
                self.canvas.blit(self.flash_surf, (0, 0))
        if self.cfg["show_fps"]:
            draw_text(self.canvas, f"FPS {int(self.clock.get_fps())}", W - 4, H - 10, GREEN, 1, "right")
        self.present()
        return True

    def shutdown(self):
        self.save.save()
        pygame.quit()

    def run(self):
        """Desktop: classic blocking loop."""
        while self.frame():
            pass
        self.shutdown()

    async def run_async(self):
        """Browser: yield to the page every frame (paced by requestAnimationFrame)."""
        while self.frame():
            await _next_web_frame()
        self.shutdown()


async def _next_web_frame():
    try:
        import js
        from pyodide.ffi import create_once_callable
        fut = asyncio.get_running_loop().create_future()

        def _cb(_ts):
            if not fut.done():
                fut.set_result(None)
        js.requestAnimationFrame(create_once_callable(_cb))
        await fut
    except ImportError:
        await asyncio.sleep(0.016)


async def main_async():
    try:
        await App().run_async()
    except Exception:
        import traceback
        traceback.print_exc()


def main():
    if WEB:
        # Pyodide: schedule on the page's event loop and return immediately
        asyncio.ensure_future(main_async())
    else:
        App().run()


if __name__ == "__main__":
    main()
