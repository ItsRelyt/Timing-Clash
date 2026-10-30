#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIMING CLASH  -  pixel edition
===============================
A one-button timing battler.  Single file, no art or sound assets needed:
every sprite, background, font and sound effect is generated in code.

    pip install pygame
    python timing_clash.py

ADVENTURE  Fight an endless ladder of monsters (a boss every 5th level).
           Hit the green zone to strike, yellow centre = PERFECT (double
           damage + stalls the enemy).  Enemies attack on a timer.  Earn
           coins, buy permanent upgrades, collect stars on every level.
DUEL       Two players (A / L) or you vs CPU.  Win the beam struggle.
STUDIO     Draw your own hero sprite.

F11 / Alt+Enter toggles fullscreen.  The window is resizable.
"""
import array
import json
import math
import os
import random
import sys

import pygame

# ------------------------------------------------------------------ constants
W, H = 320, 180            # internal resolution (scaled up with crisp pixels)
START_SCALE = 3
FPS = 60
FLOOR_Y = 142              # top of the floor strip
GROUND_Y = 146             # where fighters' feet land
BAR_Y, BAR_H, BAR_W = 30, 110, 14

# DawnBringer-16 palette
BLACK = (20, 12, 28)
PLUM = (68, 36, 52)
NAVY = (48, 52, 109)
STONE = (78, 74, 78)
BROWN = (133, 76, 48)
FOREST = (52, 101, 36)
RED = (208, 70, 72)
OLIVE = (117, 113, 97)
BLUE = (89, 125, 206)
ORANGE = (210, 125, 44)
GRAY = (133, 149, 161)
GREEN = (109, 170, 44)
SKIN = (210, 170, 153)
CYAN = (109, 194, 202)
YELLOW = (218, 212, 94)
CREAM = (222, 238, 214)
PAL = [BLACK, PLUM, NAVY, STONE, BROWN, FOREST, RED, OLIVE,
       BLUE, ORANGE, GRAY, GREEN, SKIN, CYAN, YELLOW, CREAM]
HEXCH = "0123456789abcdef"

# ------------------------------------------------------------------- settings
SETTINGS = {
    "shake": True, "particles": True, "scanlines": True, "sound": True,
    "hardcore": False, "difficulty": "NORMAL", "format": "BEST OF 3", "fps": False,
}
OPTION_ROWS = [
    ("shake", "SCREEN SHAKE", (True, False)),
    ("particles", "PARTICLES", (True, False)),
    ("scanlines", "CRT SCANLINES", (True, False)),
    ("sound", "SOUND", (True, False)),
    ("hardcore", "HARDCORE MISS (2S)", (True, False)),
    ("difficulty", "DIFFICULTY", ("EASY", "NORMAL", "HARD")),
    ("format", "DUEL FORMAT", ("SINGLE ROUND", "BEST OF 3")),
    ("fps", "FPS COUNTER", (True, False)),
]

UPGRADES = [  # key, name, description, max rank, base cost
    ("vitality", "VITALITY", "+1 MAX HEART", 5, 30),
    ("power", "POWER", "+1 BASE DAMAGE", 3, 60),
    ("focus", "WIDE ZONE", "+2 PX TARGET SIZE", 5, 25),
    ("slow", "SLOW CURSOR", "-5% CURSOR SPEED", 5, 25),
    ("armor", "IRON SKIN", "ENEMIES ATTACK 6% SLOWER", 5, 35),
    ("greed", "GREED", "+20% COIN REWARDS", 5, 20),
]
UPGRADE_KEYS = [u[0] for u in UPGRADES]


def upgrade_cost(base, rank):
    return int(round(base * (1.75 ** rank)))


# ------------------------------------------------------------------ save data
def _save_path():
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    return os.path.join(base, "timing_clash_save.json")


SAVE_PATH = _save_path()


def _valid_hero(rows):
    return (isinstance(rows, list) and len(rows) == 16 and
            all(isinstance(r, str) and len(r) == 16 and all(c == "." or c in HEXCH for c in r)
                for r in rows))


def load_save():
    data = {"highest": 1, "coins": 0, "best_score": 0, "upgrades": {}, "stars": {}, "hero": None}
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return data
    try:
        # old versions only stored "highest_unlocked_level"
        data["highest"] = max(1, int(raw.get("highest", raw.get("highest_unlocked_level", 1))))
        data["coins"] = max(0, int(raw.get("coins", 0)))
        data["best_score"] = max(0, int(raw.get("best_score", 0)))
        for k, v in raw.get("upgrades", {}).items():
            if k in UPGRADE_KEYS:
                data["upgrades"][k] = max(0, int(v))
        for k, v in raw.get("stars", {}).items():
            data["stars"][str(k)] = max(0, min(3, int(v)))
        if _valid_hero(raw.get("hero")):
            data["hero"] = raw["hero"]
        for key, _label, choices in OPTION_ROWS:
            if key in raw.get("settings", {}) and raw["settings"][key] in choices:
                SETTINGS[key] = raw["settings"][key]
    except (TypeError, ValueError, AttributeError):
        pass
    return data


def write_save(data):
    out = dict(data)
    out["settings"] = dict(SETTINGS)
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except OSError:
        pass


# -------------------------------------------------------------------- helpers
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------- 3x5 pixel font
_GLYPH_SRC = {
    "A": ".#. #.# ### #.# #.#", "B": "##. #.# ##. #.# ##.", "C": ".## #.. #.. #.. .##",
    "D": "##. #.# #.# #.# ##.", "E": "### #.. ##. #.. ###", "F": "### #.. ##. #.. #..",
    "G": ".## #.. #.# #.# .##", "H": "#.# #.# ### #.# #.#", "I": "### .#. .#. .#. ###",
    "J": "..# ..# ..# #.# .#.", "K": "#.# #.# ##. #.# #.#", "L": "#.. #.. #.. #.. ###",
    "M": "#.# ### ### #.# #.#", "N": "##. #.# #.# #.# #.#", "O": ".#. #.# #.# #.# .#.",
    "P": "##. #.# ##. #.. #..", "Q": ".#. #.# #.# ##. .##", "R": "##. #.# ##. #.# #.#",
    "S": ".## #.. .#. ..# ##.", "T": "### .#. .#. .#. .#.", "U": "#.# #.# #.# #.# ###",
    "V": "#.# #.# #.# #.# .#.", "W": "#.# #.# ### ### #.#", "X": "#.# #.# .#. #.# #.#",
    "Y": "#.# #.# .#. .#. .#.", "Z": "### ..# .#. #.. ###",
    "0": "### #.# #.# #.# ###", "1": ".#. ##. .#. .#. ###", "2": "##. ..# .#. #.. ###",
    "3": "##. ..# .#. ..# ##.", "4": "#.# #.# ### ..# ..#", "5": "### #.. ##. ..# ##.",
    "6": ".## #.. ### #.# ###", "7": "### ..# .#. .#. .#.", "8": "### #.# ### #.# ###",
    "9": "### #.# ### ..# ##.",
    " ": "... ... ... ... ...", ".": "... ... ... ... .#.", ",": "... ... ... .#. #..",
    ":": "... .#. ... .#. ...", "!": ".#. .#. .#. ... .#.", "?": "##. ..# .#. ... .#.",
    "-": "... ... ### ... ...", "+": "... .#. ### .#. ...", "/": "..# ..# .#. #.. #..",
    "%": "#.# ..# .#. #.. #.#", "'": ".#. .#. ... ... ...", "(": ".## #.. #.. #.. .##",
    ")": "##. ..# ..# ..# ##.", "[": "##. #.. #.. #.. ##.", "]": ".## ..# ..# ..# .##",
    "<": "..# .#. #.. .#. ..#", ">": "#.. .#. ..# .#. #..", "=": "... ### ... ### ...",
    "*": "#.# .#. ### .#. #.#", "_": "... ... ... ... ###", "#": "#.# ### #.# ### #.#",
    "|": ".#. .#. .#. .#. .#.", "\"": "#.# #.# ... ... ...",
}
GLYPHS = {k: v.split() for k, v in _GLYPH_SRC.items()}
_text_cache = {}


def text_w(s, scale=1):
    return max(0, len(s) * 4 * scale - scale)


def render_text(s, color, scale):
    key = (s, color, scale)
    surf = _text_cache.get(key)
    if surf is None:
        if len(_text_cache) > 700:
            _text_cache.clear()
        surf = pygame.Surface((max(1, text_w(s, scale)), 5 * scale), pygame.SRCALPHA)
        x = 0
        for ch in s.upper():
            g = GLYPHS.get(ch, GLYPHS["?"])
            for ry, row in enumerate(g):
                for rx, c in enumerate(row):
                    if c == "#":
                        surf.fill(color, (x + rx * scale, ry * scale, scale, scale))
            x += 4 * scale
        _text_cache[key] = surf
    return surf


def text(surf, s, x, y, color=CREAM, scale=1, align="left", shadow=None):
    s = str(s)
    w = text_w(s, scale)
    if align == "center":
        x -= w // 2
    elif align == "right":
        x -= w
    if shadow is not None:
        surf.blit(render_text(s, shadow, scale), (x, y + scale))
    surf.blit(render_text(s, color, scale), (x, y))
    return w


def panel(surf, x, y, w, h, fill=NAVY, border=CREAM):
    surf.fill(BLACK, (x - 1, y - 1, w + 2, h + 2))
    surf.fill(border, (x, y, w, h))
    surf.fill(fill, (x + 1, y + 1, w - 2, h - 2))
    for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
        surf.fill(BLACK, (cx, cy, 1, 1))


_shade_cache = {}


def shade(surf, rect, alpha=140, color=(0, 0, 0)):
    x, y, w, h = rect
    key = (w, h, alpha, color)
    s = _shade_cache.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((color[0], color[1], color[2], alpha))
        _shade_cache[key] = s
    surf.blit(s, (x, y))


# ----------------------------------------------------------- sprite plumbing
def rows_to_surface(rows, repl=None):
    h, w = len(rows), len(rows[0])
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                if repl:
                    ch = repl.get(ch, ch)
                s.set_at((x, y), PAL[HEXCH.index(ch)])
    return s


def cells_to_surface(cells):
    n = len(cells)
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    for y in range(n):
        for x in range(n):
            if cells[y][x] is not None:
                s.set_at((x, y), cells[y][x])
    return s


class Spr:
    """A sprite with cached flipped / tinted / scaled variants."""

    def __init__(self, surf):
        self.surf = surf
        self.w, self.h = surf.get_size()
        self._c = {}

    def get(self, flip=False, tint=None, scale=1):
        key = (flip, tint, scale)
        v = self._c.get(key)
        if v is None:
            s = self.surf
            if flip:
                s = pygame.transform.flip(s, True, False)
            if tint is not None:
                t = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
                for y in range(self.h):
                    for x in range(self.w):
                        if s.get_at((x, y))[3] > 0:
                            t.set_at((x, y), tint)
                s = t
            if scale != 1:
                s = pygame.transform.scale(s, (self.w * scale, self.h * scale))
            v = self._c[key] = s
        return v


HERO_ROWS = [
    "..0000..........",
    ".0666600000.....",
    ".0666d888820....",
    ".066dd888820...0",
    ".0668888c0c0..0f",
    ".0668888ccc0.0f0",
    "..00222222200fa0",
    "....00000000fa0.",
    "....0faaa30ef0..",
    "....0faea3ac0...",
    "....0faaa3ea0...",
    "....04444400....",
    "....0220220.....",
    "....0220220.....",
    "...044404440....",
    "....000.000.....",
]
RIVAL_SWAP = {"8": "6", "d": "9", "2": "1", "6": "e"}

HEART = [".66.66.", "6c66666", "6666666", ".66666.", "..666..", "...6..."]
COIN = [".eee.", "efee9", "eeee9", "eeee9", ".e99."]
STAR = ["...e...", "..eee..", "eeeeeee", ".eeeee.", "..eee..", ".ee.ee.", ".e...e."]
SKULL = [".fffff.", "fffffff", "f00f00f", "fffffff", ".fffff.", ".f.f.f."]
LOCK = [".aaa.", "a...a", "a...a", "aaaaa", "aa3aa", "aaaaa"]


# ------------------------------------------------- procedural monster maker
def make_monster_cells(seed, S, body, shade_c, light, boss=False):
    rng = random.Random(seed)
    u = max(1, S // 16)
    half = S // 2
    g = [[None] * S for _ in range(S)]

    def put(x, y, c):
        if 0 <= x < S and 0 <= y < S:
            g[y][x] = c

    def top_of(x):
        for y in range(S):
            if g[y][x] is not None:
                return y
        return None

    def bottom_of(x):
        for y in range(S - 1, -1, -1):
            if g[y][x] is not None:
                return y
        return None

    cy = S * (0.60 if boss else 0.55)
    ry = S * ((0.30 if boss else 0.34) + rng.random() * 0.04)
    rx = half - 1.2 * u + rng.uniform(-0.4, 0.6) * u
    for y in range(S):
        for x in range(half):
            dx = (x + 0.5 - half) / rx
            dy = (y + 0.5 - cy) / ry
            if dx * dx + dy * dy < 1.0 + rng.uniform(-0.22, 0.10):
                g[y][x] = body

    if boss:
        feats = ["legs", "arms"]
    else:
        feats = rng.sample(["horns", "ears", "legs", "arms", "spikes", "antenna", "legs"], 2)
    for f in feats:
        if f == "horns":
            x = half - rng.randint(2 * u + 1, 4 * u)
            t = top_of(x)
            if t is not None:
                for k in range(1, rng.randint(2, 4) * u + 1):
                    for d in range(u):
                        put(x - d, t - k, CREAM)
        elif f == "ears":
            x = half - rng.randint(3 * u, 5 * u)
            t = top_of(x)
            if t is not None:
                for k in range(1, 2 * u + 1):
                    for d in range(2 * u):
                        put(x - d, t - k, body if (k + d) % 3 else shade_c)
        elif f == "legs":
            lx = half - rng.randint(2 * u + 1, 4 * u)
            b = bottom_of(lx)
            if b is not None:
                for k in range(1, 2 * u + 1):
                    for d in range(2 * u):
                        if b + k <= S - 2:
                            put(lx - d, b + k, shade_c)
        elif f == "arms":
            y = int(cy) + rng.randint(-u, 2 * u)
            row = [x for x in range(S) if g[y][x] is not None]
            if row:
                for k in range(1, 2 * u + 2):
                    for d in range(u + 1):
                        put(row[0] - k, y + d, shade_c)
        elif f == "spikes":
            x = half - 2 * u
            while x > u + 1:
                t = top_of(x)
                if t is not None:
                    for k in range(1, rng.randint(1, 2) * u + 1):
                        put(x, t - k, shade_c)
                x -= 3 * u
        elif f == "antenna":
            x = half - rng.randint(2 * u, 3 * u)
            t = top_of(x)
            if t is not None:
                n = rng.randint(3, 5) * u
                for k in range(1, n):
                    put(x, t - k, shade_c)
                for a in range(u + 1):
                    for b2 in range(u + 1):
                        put(x - a, t - n - b2, light)

    for y in range(S):                      # mirror left -> right
        for x in range(half):
            g[y][S - 1 - x] = g[y][x]

    pupil = RED if boss else BLACK
    ey = int(cy - ry * 0.40)
    if rng.random() < 0.22:                 # cyclops
        ew = 4 * u
        for dy in range(3 * u):
            for dx in range(ew):
                put(half - ew // 2 + dx, ey + dy, CREAM)
        for dy in range(2 * u):
            for dx in range(2 * u):
                put(half - u + dx, ey + u + dy, pupil)
        for dx in range(ew):
            put(half - ew // 2 + dx, ey - 1, BLACK)
    else:
        ex = half - rng.randint(2 * u, 3 * u) - 1
        for side in (0, 1):
            for dy in range(2 * u):
                for dx in range(2 * u):
                    put(ex - dx if side == 0 else S - 1 - (ex - dx), ey + dy, CREAM)
            for dy in range(u):
                for dx in range(u):
                    put(ex - dx if side == 0 else S - 1 - (ex - dx), ey + u + dy, pupil)
            for dx in range(2 * u):
                put(ex - dx if side == 0 else S - 1 - (ex - dx), ey - 1, BLACK)
    if rng.random() < 0.8:                  # toothy mouth
        my = int(cy + ry * 0.40)
        mw = rng.randint(2 * u, 4 * u)
        for dy in range(u):
            for x in range(half - mw, half + mw):
                if 0 <= my + dy < S and g[my + dy][x] is not None:
                    put(x, my + dy, BLACK)
        for x in range(half - mw, half + mw):
            if (x // u) % 2 == 0 and g[my][x] is not None:
                put(x, my, CREAM)

    if boss:                                # crown
        cols = range(half - 4 * u, half + 4 * u)
        base_top = min(y for x in cols for y in range(S) if g[y][x] == body) - 1
        for x in cols:
            for k in range(u * 2):
                put(x, base_top - k, YELLOW if k else ORANGE)
        for px in (half - 4 * u, half - u, half + 2 * u):
            for k in range(u * 2, u * 4):
                for d in range(2 * u):
                    put(px + d, base_top - k, YELLOW)
        put(half - 1, base_top - u, RED)
        put(half, base_top - u, RED)

    def filled(x, y):
        return 0 <= x < S and 0 <= y < S and g[y][x] is not None

    out = [[g[y][x] for x in range(S)] for y in range(S)]
    for y in range(S):                      # light from the top-left
        for x in range(S):
            if g[y][x] == body:
                if not filled(x, y - 1) or not filled(x - 1, y):
                    out[y][x] = light
                elif not filled(x, y + 1) or not filled(x + 1, y):
                    out[y][x] = shade_c
                elif y > cy + ry * 0.5 and (x + y) % 2 == 0:
                    out[y][x] = shade_c
    g = out
    start = None                            # drop stray pixels
    for d in range(S):
        for yy in (int(cy) - d, int(cy) + d):
            if 0 <= yy < S and g[yy][half] is not None:
                start = (half, yy)
                break
        if start:
            break
    if start:
        seen, stack = {start}, [start]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < S and 0 <= ny < S and (nx, ny) not in seen and g[ny][nx] is not None:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        for y in range(S):
            for x in range(S):
                if g[y][x] is not None and (x, y) not in seen:
                    g[y][x] = None
    res = [row[:] for row in g]             # black outline
    for y in range(S):
        for x in range(S):
            if g[y][x] is None and (filled(x + 1, y) or filled(x - 1, y) or
                                    filled(x, y + 1) or filled(x, y - 1)):
                res[y][x] = BLACK
    return res


# monster colour sets per world: (body, shade, light)
WORLD_MONSTERS = [
    [(GREEN, FOREST, YELLOW), (BLUE, NAVY, CYAN), (YELLOW, ORANGE, CREAM), (SKIN, BROWN, CREAM)],
    [(NAVY, BLACK, BLUE), (GRAY, STONE, CREAM), (CYAN, BLUE, CREAM), (OLIVE, STONE, GRAY)],
    [(ORANGE, BROWN, YELLOW), (RED, PLUM, ORANGE), (YELLOW, ORANGE, CREAM), (BROWN, PLUM, ORANGE)],
    [(CYAN, BLUE, CREAM), (GRAY, STONE, CREAM), (BLUE, NAVY, CYAN), (CREAM, GRAY, CREAM)],
    [(RED, PLUM, ORANGE), (NAVY, BLACK, BLUE), (STONE, BLACK, GRAY), (PLUM, BLACK, RED)],
]

# ------------------------------------------------------------ level designer
WORLD_NAMES = ["TWILIGHT FIELDS", "CRYSTAL CAVERN", "EMBER DUNES", "FROZEN PEAKS", "SHADOW KEEP"]
ADJ = ["MOSSY", "GRIM", "RUSTY", "SPIKY", "DREAD", "WICKED", "FROSTY", "EMBER",
       "HOLLOW", "SLIMY", "FERAL", "GLOOMY"]
NOUN = ["BLOB", "BAT", "IMP", "GHOUL", "GOLEM", "WISP", "CRAB", "WYRM", "SHADE", "GNOME", "TOAD", "SLIME"]
BOSS_TITLE = ["KING", "LORD", "QUEEN", "TITAN", "OVERLORD"]
DIFF_MULT = {"EASY": (1.35, 1.2, 0.85), "NORMAL": (1.0, 1.0, 1.0), "HARD": (0.8, 0.85, 1.12)}


def level_config(n, diff="NORMAL"):
    """Fair, gradually rising difficulty.  Bosses are every 5th level."""
    boss = n % 5 == 0
    rng = random.Random(n * 7919 + 13)
    atk_m, zone_m, spd_m = DIFF_MULT[diff]
    hp = 4 + int(n * 0.8)
    if boss:
        hp = int(hp * 1.8) + 2
    drift = 0.0 if n < 4 else min(9.0, 3.0 + (n - 4) * 0.5)
    danger = 0 if n < 7 else (1 if n < 14 else 2)
    erratic = 0.0 if n < 10 else min(0.4, 0.15 + (n - 10) * 0.02)
    if boss:
        drift = max(drift, 5.0)
        danger = min(2, danger + 1)
    noun = rng.choice(NOUN)
    name = "%s %s" % (rng.choice(BOSS_TITLE), noun) if boss else "%s %s" % (rng.choice(ADJ), noun)
    mods = []
    if drift:
        mods.append("DRIFTING ZONE")
    if danger:
        mods.append("TRAPS X%d" % danger)
    if erratic:
        mods.append("ERRATIC CURSOR")
    return {
        "level": n, "boss": boss, "name": name, "hp": hp,
        "speed": min(165.0, 52.0 + n * 5.5) * spd_m,
        "zone": max(8.0, 34.0 - n * 1.25) * zone_m,
        "interval": max(3.0, 7.5 - n * 0.17) * atk_m,
        "drift": drift, "danger": danger, "erratic": erratic, "mods": mods,
        "world": ((n - 1) // 5) % 5, "size": 32 if boss else 16,
    }


# ---------------------------------------------------------------------- audio
SFX = {
    "select": [(900, 900, 0.04, "sq", 0.25)],
    "confirm": [(660, 660, 0.05, "sq", 0.25), (990, 990, 0.09, "sq", 0.25)],
    "back": [(500, 300, 0.09, "sq", 0.25)],
    "hit": [(0, 0, 0.05, "noise", 0.5), (300, 120, 0.1, "sq", 0.3)],
    "crit": [(0, 0, 0.04, "noise", 0.5), (660, 660, 0.05, "sq", 0.3),
             (880, 880, 0.05, "sq", 0.3), (1320, 1320, 0.14, "sq", 0.3)],
    "miss": [(220, 90, 0.25, "saw", 0.3)],
    "hurt": [(0, 0, 0.12, "noise", 0.6), (140, 60, 0.22, "sq", 0.35)],
    "coin": [(988, 988, 0.06, "sq", 0.25), (1319, 1319, 0.14, "sq", 0.25)],
    "win": [(523, 523, 0.1, "sq", 0.3), (659, 659, 0.1, "sq", 0.3),
            (784, 784, 0.1, "sq", 0.3), (1046, 1046, 0.32, "sq", 0.3)],
    "lose": [(392, 392, 0.15, "tri", 0.45), (330, 330, 0.15, "tri", 0.45),
             (262, 262, 0.15, "tri", 0.45), (196, 150, 0.4, "tri", 0.45)],
    "beep": [(440, 440, 0.1, "sq", 0.25)],
    "go": [(880, 880, 0.25, "sq", 0.3)],
    "ko": [(0, 0, 0.15, "noise", 0.6), (400, 60, 0.5, "saw", 0.3)],
    "deny": [(150, 150, 0.08, "sq", 0.25)],
    "buy": [(784, 784, 0.07, "sq", 0.3), (988, 988, 0.07, "sq", 0.3), (1319, 1319, 0.15, "sq", 0.3)],
}


def synth(segs, rate):
    out = array.array("h")
    for f0, f1, dur, wave, vol in segs:
        n = max(1, int(rate * dur))
        ph = 0.0
        atk = rate * 0.002 + 1
        for i in range(n):
            k = i / n
            ph += (f0 + (f1 - f0) * k) / rate
            p = ph % 1.0
            if wave == "sq":
                v = 1.0 if p < 0.5 else -1.0
            elif wave == "tri":
                v = 4.0 * abs(p - 0.5) - 1.0
            elif wave == "saw":
                v = 2.0 * p - 1.0
            else:
                v = random.uniform(-1.0, 1.0)
            out.append(int(v * vol * min(1.0, i / atk) * (1.0 - k) ** 0.5 * 30000))
    return out


class Audio:
    def __init__(self):
        self.sounds = {}
        self.ok = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            rate, fmt, ch = pygame.mixer.get_init()
            if fmt != -16:
                return
            for name, segs in SFX.items():
                s = synth(segs, rate)
                if ch == 2:
                    s = array.array("h", [v for v in s for _ in (0, 1)])
                self.sounds[name] = pygame.mixer.Sound(buffer=s.tobytes())
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and SETTINGS["sound"]:
            try:
                self.sounds[name].play()
            except Exception:
                pass


# ---------------------------------------------------------------- backgrounds
WORLD_THEMES = [
    dict(sky=[BLACK, NAVY, PLUM, RED, ORANGE], far=PLUM, near=FOREST, floor=GREEN, floor2=FOREST, kind="meadow"),
    dict(sky=[BLACK, BLACK, PLUM, NAVY, NAVY], far=NAVY, near=STONE, floor=OLIVE, floor2=STONE, kind="cave"),
    dict(sky=[RED, ORANGE, ORANGE, YELLOW, CREAM], far=ORANGE, near=BROWN, floor=ORANGE, floor2=BROWN, kind="desert"),
    dict(sky=[NAVY, BLUE, BLUE, CYAN, CREAM], far=GRAY, near=CREAM, floor=CREAM, floor2=CYAN, kind="ice"),
    dict(sky=[BLACK, BLACK, PLUM, PLUM, RED], far=NAVY, near=BLACK, floor=STONE, floor2=BLACK, kind="keep"),
]


def _ridge(s, base, amp, color, seed, sharp=False, cap=None):
    rng = random.Random(seed)
    p = [rng.uniform(0, 6.28) for _ in range(3)]
    for x in range(W):
        v = math.sin(x * 0.021 + p[0]) + 0.6 * math.sin(x * 0.047 + p[1]) + 0.3 * math.sin(x * 0.11 + p[2])
        if sharp:
            v = abs(v) * 1.2 - 0.6
        top = int(base - amp * 0.5 * v)
        s.fill(color, (x, top, 1, FLOOR_Y - top))
        if cap:
            s.fill(cap, (x, top, 1, 2 + (x * 7 + seed) % 3))


def make_background(wi):
    th = WORLD_THEMES[wi]
    rng = random.Random(wi * 101 + 5)
    s = pygame.Surface((W, H))
    sky = th["sky"]
    n = len(sky)
    bh = FLOOR_Y / n
    for i, c in enumerate(sky):
        y0, y1 = int(i * bh), int((i + 1) * bh)
        s.fill(c, (0, y0, W, y1 - y0))
        if i + 1 < n:
            nxt = sky[i + 1]
            for k, yy in enumerate(range(y1 - 4, y1)):
                mod = (4, 2, 2, 4)[k]
                for xx in range(W):
                    if (xx + yy) % mod == 0 and (mod == 2 or yy % 2 == 0):
                        s.set_at((xx, yy), nxt)
    kind = th["kind"]
    if kind in ("meadow", "keep"):
        for _ in range(55):
            x, y = rng.randrange(W), rng.randrange(0, 70)
            s.set_at((x, y), rng.choice([CREAM, CREAM, YELLOW, GRAY]))
    if kind == "desert":
        pygame.draw.circle(s, YELLOW, (238, 96), 24)
        pygame.draw.circle(s, CREAM, (238, 96), 15)
    if kind == "keep":
        pygame.draw.circle(s, CREAM, (70, 38), 14)
        for cx, cyy in ((65, 34), (74, 42), (68, 45)):
            pygame.draw.circle(s, GRAY, (cx, cyy), 2)
    if kind == "cave":
        x = 0
        while x < W:
            ln, wd = rng.randint(8, 34), rng.randint(5, 11)
            for k in range(ln):
                half = max(0, (wd * (ln - k)) // (ln * 2))
                s.fill(PLUM, (x + wd // 2 - half, k, half * 2 + 1, 1))
            x += wd + rng.randint(2, 14)
    _ridge(s, 108, 40, th["far"], wi * 3 + 1, sharp=(kind == "ice"), cap=CREAM if kind == "ice" else None)
    _ridge(s, 128, 26, th["near"], wi * 3 + 2)
    if kind == "keep":                      # castle silhouette
        for tx, tw, tt in ((190, 16, 70), (214, 12, 84), (232, 20, 62), (258, 14, 90)):
            s.fill(BLACK, (tx, tt, tw, FLOOR_Y - tt))
            for cx in range(tx, tx + tw, 4):
                s.fill(BLACK, (cx, tt - 3, 2, 3))
            s.fill(YELLOW, (tx + tw // 2 - 1, tt + 10, 2, 3))
    # floor
    s.fill(th["floor"], (0, FLOOR_Y, W, H - FLOOR_Y))
    s.fill(CREAM if kind == "ice" else th["floor2"], (0, FLOOR_Y, W, 2))
    if kind in ("cave", "keep"):
        for yy in range(FLOOR_Y + 8, H, 9):
            s.fill(th["floor2"], (0, yy, W, 1))
            off = (yy // 9 % 2) * 12
            for xx in range(off, W, 24):
                s.fill(th["floor2"], (xx, yy, 1, 9))
    else:
        for _ in range(90):
            x, y = rng.randrange(W), rng.randrange(FLOOR_Y + 3, H)
            s.fill(th["floor2"], (x, y, rng.choice([1, 2, 3]), 1))
        if kind == "meadow":
            for _ in range(26):
                x = rng.randrange(W)
                s.fill(GREEN, (x, FLOOR_Y - 2, 1, 2))
                s.fill(FOREST, (x + 1, FLOOR_Y - 1, 1, 1))
    if kind == "cave":
        for _ in range(9):
            x, hgt = rng.randrange(W), rng.randint(4, 9)
            for k in range(hgt):
                half = (hgt - k) // 3
                s.fill(rng.choice([CYAN, BLUE]), (x - half, FLOOR_Y - k, half * 2 + 1, 1))
    return s


class Ambient:
    KINDS = ["twinkle", "dust", "ember", "snow", "twinkle"]

    def __init__(self, wi):
        rng = random.Random(wi + 77)
        self.kind = self.KINDS[wi]
        self.t = 0.0
        self.p = [[rng.uniform(0, W), rng.uniform(0, FLOOR_Y - 8), rng.uniform(0.5, 1.5),
                   rng.uniform(0, 6.28)] for _ in range(34)]

    def update(self, dt):
        self.t += dt
        for p in self.p:
            if self.kind == "dust":
                p[0] += 7 * p[2] * dt
                p[1] += math.sin(self.t + p[3]) * 4 * dt
            elif self.kind == "ember":
                p[1] -= 16 * p[2] * dt
                p[0] += math.sin(self.t * 2 + p[3]) * 8 * dt
                if p[1] < 0:
                    p[1] = FLOOR_Y - 2
            elif self.kind == "snow":
                p[1] += 20 * p[2] * dt
                p[0] += math.sin(self.t + p[3]) * 9 * dt
                if p[1] > FLOOR_Y:
                    p[1] = 0
            p[0] %= W

    def draw(self, s):
        for p in self.p:
            x, y = int(p[0]), int(p[1])
            if self.kind == "twinkle":
                if math.sin(self.t * 2.5 * p[2] + p[3]) > 0.75:
                    s.fill(CREAM, (x, y // 2, 1, 1))
            elif self.kind == "dust":
                s.fill(GRAY if p[2] < 1 else CYAN, (x, y, 1, 1))
            elif self.kind == "ember":
                s.fill(YELLOW if p[2] > 1 else ORANGE, (x, y, 1, 1))
            else:
                s.fill(CREAM, (x, y, 1 + (p[2] > 1.2), 1 + (p[2] > 1.2)))


class Assets:
    def __init__(self, hero_rows=None):
        self.bgs = {}
        self.monsters = {}
        self.icon = {
            "heart": Spr(rows_to_surface(HEART)),
            "heart_empty": Spr(rows_to_surface(HEART, {"6": "3", "c": "3"})),
            "coin": Spr(rows_to_surface(COIN)),
            "star": Spr(rows_to_surface(STAR)),
            "star_empty": Spr(rows_to_surface(STAR, {"e": "3"})),
            "skull": Spr(rows_to_surface(SKULL)),
            "lock": Spr(rows_to_surface(LOCK)),
        }
        self.rival = Spr(rows_to_surface(HERO_ROWS, RIVAL_SWAP))
        self.set_hero(hero_rows)

    def set_hero(self, rows):
        self.hero = Spr(rows_to_surface(rows or HERO_ROWS))

    def background(self, wi):
        if wi not in self.bgs:
            self.bgs[wi] = make_background(wi)
        return self.bgs[wi]

    def monster(self, cfg):
        key = cfg["level"]
        if key not in self.monsters:
            pal = WORLD_MONSTERS[cfg["world"]]
            rng = random.Random(key * 131 + 5)
            body, sh, li = pal[rng.randrange(len(pal))]
            cells = make_monster_cells(key * 31 + 7, cfg["size"], body, sh, li, cfg["boss"])
            self.monsters[key] = Spr(cells_to_surface(cells))
        return self.monsters[key]


# ------------------------------------------------------------------------ fx
class FX:
    def __init__(self):
        self.parts, self.floats, self.slashes = [], [], []

    def burst(self, x, y, color, n=12, speed=70, up=30, life=0.5, size=1, grav=160):
        if not SETTINGS["particles"]:
            return
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.3, 1.0) * speed
            self.parts.append([x, y, math.cos(a) * sp, math.sin(a) * sp - up,
                               life * random.uniform(0.6, 1.0), color, size, grav])

    def text(self, x, y, s, color=CREAM, scale=1, life=0.8):
        self.floats.append([x, y, s, color, life, scale])

    def slash(self, x, y):
        self.slashes.append([x, y, 0.0])

    def update(self, dt):
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += p[7] * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        for f in self.floats:
            f[1] -= 18 * dt
            f[4] -= dt
        self.floats = [f for f in self.floats if f[4] > 0]
        for s in self.slashes:
            s[2] += dt
        self.slashes = [s for s in self.slashes if s[2] < 0.22]

    def draw(self, surf):
        for p in self.parts:
            surf.fill(p[5], (int(p[0]), int(p[1]), p[6], p[6]))
        for s in self.slashes:
            k = s[2] / 0.22
            ln = int(20 * min(1.0, k * 2.5))
            col = CREAM if k < 0.6 else GRAY
            for i in range(ln):
                surf.fill(col, (s[0] - 10 + i, s[1] - 10 + i, 2, 2))
                if i > 3:
                    surf.fill(col, (s[0] - 6 + i, s[1] - 10 + i, 1, 1))
        for f in self.floats:
            text(surf, f[2], int(f[0]), int(f[1]), f[3], f[5], "center", BLACK)


# ----------------------------------------------------------------- timing bar
class TimingBar:
    """Vertical bar with a bouncing cursor and a target zone."""

    def __init__(self, x, y=BAR_Y, w=BAR_W, h=BAR_H):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.cursor = 0.0
        self.dir = 1
        self.speed = self.base_speed = 80.0
        self.zone_h = 26.0
        self.zone_base = 40.0
        self.drift = 0.0
        self.phase = 0.0
        self.erratic = 0.0
        self.n_danger = 0
        self.danger = []
        self.freeze = 0.0
        self.t = 0.0
        self.flash = 0.0
        self.flash_col = GREEN
        self.new_target()

    def set_speed(self, sp):
        self.speed = self.base_speed = sp

    def zone(self):
        y0 = self.zone_base + math.sin(self.t * 1.7 + self.phase) * self.drift
        return clamp(y0, 0, self.h - self.zone_h), self.zone_h

    def perfect_half(self):
        return max(1.5, self.zone_h * 0.17)

    def new_target(self):
        mx = self.h - self.zone_h
        amp = self.drift
        if mx < 2 * amp:
            amp = self.drift = 0.0
        prev = self.zone_base
        for _ in range(20):
            y = random.uniform(amp, mx - amp)
            if abs(y - prev) > self.zone_h * 0.7:
                break
        self.zone_base = y
        self.phase = random.uniform(0, math.tau)
        self.danger = []
        lo, hi = y - amp - 3, y + self.zone_h + amp + 3
        for _ in range(self.n_danger):
            dh = random.randint(6, 10)
            for _try in range(30):
                dy = random.uniform(0, self.h - dh)
                if dy + dh < lo or dy > hi:
                    if all(dy + dh < d[0] - 2 or dy > d[0] + d[1] + 2 for d in self.danger):
                        self.danger.append((dy, dh))
                        break

    def update(self, dt):
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        if self.freeze > 0:
            self.freeze -= dt
            return
        sp = self.speed * (1 + self.erratic * math.sin(self.t * 2.4))
        self.cursor += sp * dt * self.dir
        if self.cursor <= 0:
            self.cursor, self.dir = 0.0, 1
        elif self.cursor >= self.h:
            self.cursor, self.dir = float(self.h), -1

    def strike(self):
        """Returns None (frozen), 'perfect', 'hit', 'miss' or 'danger'."""
        if self.freeze > 0:
            return None
        c = self.cursor
        for dy, dh in self.danger:
            if dy <= c <= dy + dh:
                return "danger"
        zy, zh = self.zone()
        if zy - 0.5 <= c <= zy + zh + 0.5:
            if abs(c - (zy + zh / 2)) <= self.perfect_half():
                return "perfect"
            return "hit"
        return "miss"

    def mark(self, col):
        self.flash, self.flash_col = 0.14, col

    def draw(self, s, accent):
        x, y, w, h = self.x, self.y, self.w, self.h
        s.fill(BLACK, (x - 3, y - 3, w + 6, h + 6))
        s.fill(self.flash_col if self.flash > 0 else accent, (x - 2, y - 2, w + 4, h + 4))
        s.fill(BLACK, (x - 1, y - 1, w + 2, h + 2))
        s.fill(NAVY, (x, y, w, h))
        for ty in range(0, h, 10):
            s.fill(BLUE, (x, y + ty, 2, 1))
            s.fill(BLUE, (x + w - 2, y + ty, 2, 1))
        for dy, dh in self.danger:
            ry = y + int(dy)
            s.fill(RED, (x, ry, w, int(dh)))
            for yy in range(int(dh)):
                for xx in range(w):
                    if (xx + yy) % 4 < 2:
                        s.fill(PLUM, (x + xx, ry + yy, 1, 1))
        zy, zh = self.zone()
        zy0 = y + int(zy)
        s.fill(FOREST, (x, zy0, w, int(zh)))
        s.fill(GREEN, (x, zy0 + 1, w, max(1, int(zh) - 2)))
        ph = self.perfect_half()
        c0 = int(round(zy + zh / 2 - ph))
        c1 = int(round(zy + zh / 2 + ph))
        s.fill(YELLOW, (x + 2, y + c0, w - 4, max(2, c1 - c0)))
        cy = y + int(self.cursor)
        col = RED if self.freeze > 0 else CREAM
        s.fill(BLACK, (x - 1, cy - 2, w + 2, 4))
        s.fill(col, (x, cy - 1, w, 2))
        for i in range(5):
            hb = 9 - 2 * i
            s.fill(BLACK, (x - 10 + i, cy - hb // 2, 1, hb))
            s.fill(BLACK, (x + w + 9 - i, cy - hb // 2, 1, hb))
        for i in range(4):
            hh = 7 - 2 * i
            s.fill(col, (x - 9 + i, cy - hh // 2, 1, hh))
            s.fill(col, (x + w + 8 - i, cy - hh // 2, 1, hh))


# --------------------------------------------------------------------- scenes
K = pygame
KEY_ENTER = (pygame.K_RETURN, pygame.K_KP_ENTER)
KEY_UP = (pygame.K_UP, pygame.K_w)
KEY_DOWN = (pygame.K_DOWN, pygame.K_s)


class Scene:
    def __init__(self, g):
        self.g = g

    def handle(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, s):
        pass


def draw_hearts(s, g, x, y, hp, mx):
    for i in range(mx):
        s.blit(g.assets.icon["heart" if i < hp else "heart_empty"].get(), (x + i * 8, y))


def menu_bg(g, s):
    s.blit(g.assets.background(0), (0, 0))
    shade(s, (0, 0, W, H), 150)


class TitleScene(Scene):
    ITEMS = ["ADVENTURE", "DUEL  2 PLAYERS", "DUEL  VS CPU", "UPGRADES",
             "SPRITE STUDIO", "OPTIONS", "HOW TO PLAY", "QUIT"]

    def __init__(self, g):
        super().__init__(g)
        self.sel = 0
        self.t = 0.0
        self.amb = Ambient(0)
        self.boss = g.assets.monster(level_config(5))

    def handle(self, e):
        g = self.g
        if e.type != pygame.KEYDOWN:
            return
        if e.key in KEY_UP:
            self.sel = (self.sel - 1) % len(self.ITEMS)
            g.play("select")
        elif e.key in KEY_DOWN:
            self.sel = (self.sel + 1) % len(self.ITEMS)
            g.play("select")
        elif e.key in KEY_ENTER or e.key == pygame.K_SPACE:
            self.activate()
        elif e.key == pygame.K_ESCAPE:
            g.quit()

    def activate(self):
        g, i = self.g, self.sel
        g.play("confirm")
        if i == 0:
            g.go(LevelSelect(g))
        elif i == 1:
            g.go(Duel(g, cpu=False))
        elif i == 2:
            g.go(Duel(g, cpu=True))
        elif i == 3:
            g.go(ShopScene(g, lambda: TitleScene(g)))
        elif i == 4:
            g.go(Studio(g))
        elif i == 5:
            g.go(OptionsScene(g))
        elif i == 6:
            g.go(HowToScene(g))
        else:
            g.quit()

    def update(self, dt):
        self.t += dt
        self.amb.update(dt)

    def draw(self, s):
        g = self.g
        s.blit(g.assets.background(0), (0, 0))
        self.amb.draw(s)
        bob = int(self.t * 3) % 2
        s.blit(g.assets.hero.get(scale=2), (16, 10 + bob * 2))
        s.blit(self.boss.get(), (260, 6 + (1 - bob) * 2))
        text(s, "TIMING CLASH", W // 2, 12, YELLOW, 4, "center", ORANGE)
        text(s, "PIXEL EDITION", W // 2, 40, CYAN, 1, "center")
        shade(s, (88, 52, 144, 116), 170)
        for i, item in enumerate(self.ITEMS):
            y = 57 + i * 13
            if i == self.sel:
                text(s, "> " + item + " <", W // 2, y, YELLOW, 2, "center")
            else:
                text(s, item, W // 2, y, CREAM, 2, "center")
        text(s, "BEST SCORE %d" % g.save["best_score"], 6, 172, GRAY)
        s.blit(g.assets.icon["coin"].get(), (W - 40, 171))
        text(s, str(g.save["coins"]), W - 6, 172, YELLOW, 1, "right")


class LevelSelect(Scene):
    COLS, ROWS = 5, 4

    def __init__(self, g):
        super().__init__(g)
        self.sel = g.save["highest"]
        self.t = 0.0

    def handle(self, e):
        g = self.g
        if e.type != pygame.KEYDOWN:
            return
        hi = g.save["highest"]
        old = self.sel
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            g.play("back")
            g.go(TitleScene(g))
        elif e.key in (pygame.K_LEFT, pygame.K_a):
            self.sel = max(1, self.sel - 1)
        elif e.key in (pygame.K_RIGHT, pygame.K_d):
            self.sel = min(hi, self.sel + 1)
        elif e.key in KEY_UP:
            self.sel = max(1, self.sel - self.COLS)
        elif e.key in KEY_DOWN:
            self.sel = min(hi, self.sel + self.COLS)
        elif e.key == pygame.K_PAGEUP:
            self.sel = max(1, self.sel - 20)
        elif e.key == pygame.K_PAGEDOWN:
            self.sel = min(hi, self.sel + 20)
        elif e.key in KEY_ENTER or e.key == pygame.K_SPACE:
            g.play("confirm")
            g.start_run(self.sel)
            return
        if self.sel != old:
            g.play("select")

    def update(self, dt):
        self.t += dt

    def draw(self, s):
        g = self.g
        menu_bg(g, s)
        hi = g.save["highest"]
        per = self.COLS * self.ROWS
        page = (self.sel - 1) // per
        text(s, "SELECT LEVEL", W // 2, 6, YELLOW, 2, "center", BLACK)
        pages = max(1, (hi + 4) // per + 1)
        text(s, "PAGE %d/%d" % (page + 1, pages), W - 6, 8, GRAY, 1, "right")
        cw, ch, gap = 52, 26, 4
        x0 = (W - (self.COLS * cw + (self.COLS - 1) * gap)) // 2
        for i in range(per):
            lv = page * per + i + 1
            x = x0 + (i % self.COLS) * (cw + gap)
            y = 22 + (i // self.COLS) * (ch + gap)
            unlocked = lv <= hi
            boss = lv % 5 == 0
            sel = lv == self.sel
            border = YELLOW if sel else (RED if boss and unlocked else (STONE if unlocked else PLUM))
            panel(s, x, y, cw, ch, NAVY if unlocked else BLACK, border)
            if sel:
                s.fill(YELLOW, (x + 1, y + 1, cw - 2, 1))
            if unlocked:
                text(s, str(lv), x + cw // 2, y + 4, CREAM, 2, "center")
                stars = g.save["stars"].get(str(lv), 0)
                for k in range(3):
                    s.blit(g.assets.icon["star" if k < stars else "star_empty"].get(), (x + 14 + k * 8, y + 16))
                if boss:
                    s.blit(g.assets.icon["skull"].get(), (x + cw - 9, y + 3))
            else:
                s.blit(g.assets.icon["lock"].get(), (x + cw // 2 - 2, y + 10))
        cfg = level_config(self.sel, SETTINGS["difficulty"])
        panel(s, 8, 142, W - 16, 32, BLACK, STONE)
        text(s, "LV %d  %s" % (cfg["level"], cfg["name"]), 14, 146, RED if cfg["boss"] else YELLOW)
        text(s, "WORLD: " + WORLD_NAMES[cfg["world"]], W - 14, 146, CYAN, 1, "right")
        text(s, "HP %d   ATK EVERY %.1fS   SPEED %d" % (cfg["hp"], cfg["interval"], cfg["speed"]), 14, 155, CREAM)
        mods = ", ".join(cfg["mods"]) if cfg["mods"] else "NO SPECIAL RULES"
        text(s, mods, 14, 164, GRAY)
        text(s, "ENTER: FIGHT   ESC: BACK", W - 14, 164, GRAY, 1, "right")


class ShopScene(Scene):
    def __init__(self, g, back):
        super().__init__(g)
        self.back = back
        self.sel = 0
        self.msg = ""
        self.msg_t = 0.0
        self.t = 0.0

    def handle(self, e):
        g = self.g
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            g.play("back")
            g.go(self.back())
        elif e.key in KEY_UP:
            self.sel = (self.sel - 1) % len(UPGRADES)
            g.play("select")
        elif e.key in KEY_DOWN:
            self.sel = (self.sel + 1) % len(UPGRADES)
            g.play("select")
        elif e.key in KEY_ENTER or e.key == pygame.K_SPACE:
            key, name, _d, mx, base = UPGRADES[self.sel]
            rank = g.save["upgrades"].get(key, 0)
            cost = upgrade_cost(base, rank)
            if rank >= mx:
                self.say("ALREADY MAXED")
                g.play("deny")
            elif g.save["coins"] < cost:
                self.say("NOT ENOUGH COINS")
                g.play("deny")
            else:
                g.save["coins"] -= cost
                g.save["upgrades"][key] = rank + 1
                if key == "vitality":
                    g.run_hp += 1
                g.play("buy")
                self.say("%s UPGRADED!" % name)
                g.save_now()

    def say(self, m):
        self.msg, self.msg_t = m, 1.5

    def update(self, dt):
        self.t += dt
        self.msg_t -= dt

    def draw(self, s):
        g = self.g
        menu_bg(g, s)
        text(s, "UPGRADES", 10, 6, YELLOW, 2, "left", BLACK)
        s.blit(g.assets.icon["coin"].get(), (W - 56, 8))
        text(s, str(g.save["coins"]), W - 10, 8, YELLOW, 1, "right")
        for i, (key, name, desc, mx, base) in enumerate(UPGRADES):
            y = 24 + i * 23
            rank = g.save["upgrades"].get(key, 0)
            sel = i == self.sel
            panel(s, 8, y, W - 16, 21, NAVY if sel else BLACK, YELLOW if sel else STONE)
            text(s, name, 14, y + 3, YELLOW if sel else CREAM, 2)
            text(s, desc, 14, y + 14, GRAY)
            for k in range(mx):
                s.fill(GREEN if k < rank else PLUM, (190 + k * 7, y + 4, 5, 5))
            if rank >= mx:
                text(s, "MAX", W - 14, y + 13, GREEN, 1, "right")
            else:
                cost = upgrade_cost(base, rank)
                can = g.save["coins"] >= cost
                s.blit(g.assets.icon["coin"].get(), (W - 14 - text_w(str(cost)) - 7, y + 12))
                text(s, str(cost), W - 14, y + 13, YELLOW if can else RED, 1, "right")
        if self.msg_t > 0:
            text(s, self.msg, W // 2, 168, CREAM, 1, "center", BLACK)
        else:
            text(s, "UP/DOWN: PICK   ENTER: BUY   ESC: BACK", W // 2, 168, GRAY, 1, "center")


class OptionsScene(Scene):
    def __init__(self, g):
        super().__init__(g)
        self.sel = 0
        self.confirm = False
        self.rows = len(OPTION_ROWS) + 2

    def handle(self, e):
        g = self.g
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            g.save_now()
            g.play("back")
            g.go(TitleScene(g))
            return
        if e.key in KEY_UP:
            self.sel = (self.sel - 1) % self.rows
            self.confirm = False
            g.play("select")
        elif e.key in KEY_DOWN:
            self.sel = (self.sel + 1) % self.rows
            self.confirm = False
            g.play("select")
        elif e.key in KEY_ENTER or e.key in (pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT):
            n = len(OPTION_ROWS)
            if self.sel < n:
                key, _l, choices = OPTION_ROWS[self.sel]
                step = -1 if e.key == pygame.K_LEFT else 1
                SETTINGS[key] = choices[(choices.index(SETTINGS[key]) + step) % len(choices)]
                g.play("select")
            elif self.sel == n:
                if self.confirm:
                    g.reset_progress()
                    self.confirm = False
                    g.play("lose")
                else:
                    self.confirm = True
                    g.play("deny")
            else:
                g.save_now()
                g.play("back")
                g.go(TitleScene(g))

    def draw(self, s):
        menu_bg(self.g, s)
        text(s, "OPTIONS", W // 2, 6, YELLOW, 2, "center", BLACK)
        n = len(OPTION_ROWS)
        for i in range(self.rows):
            y = 26 + i * 13
            sel = i == self.sel
            col = YELLOW if sel else CREAM
            if i < n:
                key, label, _c = OPTION_ROWS[i]
                v = SETTINGS[key]
                if v is True:
                    vs, vc = "ON", GREEN
                elif v is False:
                    vs, vc = "OFF", RED
                else:
                    vs, vc = v, CYAN
                text(s, ("> " if sel else "  ") + label, 24, y, col, 2)
                text(s, vs, W - 24, y, vc, 2, "right")
            elif i == n:
                label = "SURE? PRESS ENTER AGAIN" if self.confirm else "ERASE PROGRESS"
                text(s, ("> " if sel else "  ") + label, 24, y, RED if (self.confirm or sel) else GRAY, 2)
            else:
                text(s, ("> " if sel else "  ") + "BACK", 24, y, col, 2)
        text(s, "UP/DOWN: PICK   LEFT/RIGHT/ENTER: CHANGE   F11: FULLSCREEN", W // 2, 170, GRAY, 1, "center")


class HowToScene(Scene):
    PAGES = [
        ("ADVENTURE", [
            "A CURSOR SLIDES UP AND DOWN THE BAR.",
            "PRESS SPACE (OR A) WHEN IT IS INSIDE THE",
            "GREEN ZONE TO STRIKE THE MONSTER.",
            "",
            "YELLOW CENTRE = PERFECT: DOUBLE DAMAGE",
            "AND THE ENEMY'S ATTACK IS DELAYED.",
            "MISS = CURSOR FREEZES. RED TRAPS HURT!",
            "",
            "WATCH THE ATK METER: WHEN IT FILLS THE",
            "ENEMY HITS YOU. LOSE ALL HEARTS = DEFEAT.",
            "COMBOS ADD DAMAGE. WIN COINS, BUY UPGRADES.",
        ]),
        ("DUEL", [
            "TWO FIGHTERS FIRE BEAMS AT EACH OTHER.",
            "EACH HIT PUSHES THE CLASH POINT BACK.",
            "",
            "PLAYER 1: A          PLAYER 2: L",
            "(VS CPU: P1 USES A OR SPACE)",
            "",
            "STREAKS AND PERFECT HITS PUSH HARDER.",
            "PUSH THE CLASH TO THE EDGE FOR A K.O.",
            "OTHERWISE THE BIGGER PUSH WINS AT 0:00.",
            "TIED? SUDDEN DEATH - NEXT HIT WINS.",
            "",
            "ESC / P PAUSES.",
        ]),
    ]

    def __init__(self, g):
        super().__init__(g)
        self.page = 0
        self.bar = TimingBar(40, 40, 14, 100)
        self.bar.set_speed(55)
        self.t = 0.0

    def handle(self, e):
        g = self.g
        if e.type != pygame.KEYDOWN:
            return
        if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN):
            g.play("back")
            g.go(TitleScene(g))
        elif e.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d, pygame.K_SPACE):
            self.page = 1 - self.page
            g.play("select")

    def update(self, dt):
        self.bar.update(dt)

    def draw(self, s):
        menu_bg(self.g, s)
        title, lines = self.PAGES[self.page]
        text(s, "HOW TO PLAY: " + title, W // 2, 6, YELLOW, 2, "center", BLACK)
        if self.page == 0:
            self.bar.draw(s, CYAN)
            text(s, "ZONE", 62, 62, GREEN)
            text(s, "PERFECT", 62, 88, YELLOW)
            text(s, "TRAP", 62, 110, RED)
        x0 = 100 if self.page == 0 else 24
        for i, ln in enumerate(lines):
            text(s, ln, x0, 30 + i * 11, CREAM)
        text(s, "LEFT/RIGHT: PAGE   ESC: BACK", W // 2, 170, GRAY, 1, "center")


class Studio(Scene):
    CELL, X0, Y0 = 8, 20, 26

    def __init__(self, g):
        super().__init__(g)
        rows = g.save["hero"] or HERO_ROWS
        self.grid = [list(r) for r in rows]
        self.color = 8
        self.t = 0.0

    def surface(self):
        return rows_to_surface(["".join(r) for r in self.grid])

    def cell_at(self, mx, my):
        cx, cy = (mx - self.X0) // self.CELL, (my - self.Y0) // self.CELL
        return (cx, cy) if 0 <= cx < 16 and 0 <= cy < 16 else None

    def swatch_at(self, mx, my):
        for i in range(16):
            x, y = 176 + (i % 8) * 17, 40 + (i // 8) * 17
            if x <= mx < x + 15 and y <= my < y + 15:
                return i
        return None

    def leave(self):
        self.g.save["hero"] = ["".join(r) for r in self.grid]
        self.g.assets.set_hero(self.g.save["hero"])
        self.g.save_now()
        self.g.go(TitleScene(self.g))

    def handle(self, e):
        g = self.g
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            i = self.swatch_at(*g.mouse_pos())
            if i is not None:
                self.color = i
                g.play("select")
        if e.type != pygame.KEYDOWN:
            return
        if e.key == pygame.K_ESCAPE:
            g.play("confirm")
            self.leave()
        elif e.key == pygame.K_c:
            self.grid = [["."] * 16 for _ in range(16)]
        elif e.key == pygame.K_r:
            self.grid = [list(r) for r in HERO_ROWS]
        elif e.key == pygame.K_f:
            self.grid = [r[::-1] for r in self.grid]
        elif e.key == pygame.K_LEFTBRACKET:
            self.color = (self.color - 1) % 16
        elif e.key == pygame.K_RIGHTBRACKET:
            self.color = (self.color + 1) % 16
        elif e.key == pygame.K_LEFT:
            self.grid = [r[1:] + ["."] for r in self.grid]
        elif e.key == pygame.K_RIGHT:
            self.grid = [["."] + r[:-1] for r in self.grid]
        elif e.key == pygame.K_UP:
            self.grid = self.grid[1:] + [["."] * 16]
        elif e.key == pygame.K_DOWN:
            self.grid = [["."] * 16] + self.grid[:-1]

    def update(self, dt):
        self.t += dt
        b = pygame.mouse.get_pressed()
        if b[0] or b[2]:
            c = self.cell_at(*self.g.mouse_pos())
            if c:
                self.grid[c[1]][c[0]] = HEXCH[self.color] if b[0] else "."

    def draw(self, s):
        menu_bg(self.g, s)
        text(s, "SPRITE STUDIO", W // 2, 6, YELLOW, 2, "center", BLACK)
        n = self.CELL
        panel(s, self.X0 - 3, self.Y0 - 3, 16 * n + 6, 16 * n + 6, BLACK, STONE)
        for y in range(16):
            for x in range(16):
                ch = self.grid[y][x]
                col = PAL[HEXCH.index(ch)] if ch != "." else (GRAY if (x + y) % 2 else OLIVE)
                s.fill(col, (self.X0 + x * n, self.Y0 + y * n, n, n))
        for i in range(16):
            x, y = 176 + (i % 8) * 17, 40 + (i // 8) * 17
            s.fill(CREAM if i == self.color else BLACK, (x - 1, y - 1, 17, 17))
            s.fill(PAL[i], (x, y, 15, 15))
        text(s, "COLOR " + HEXCH[self.color].upper(), 176, 76, CREAM)
        spr = Spr(self.surface())
        panel(s, 176, 90, 130, 64, BLACK, STONE)
        s.fill(GREEN, (177, 140, 128, 13))
        bob = int(self.t * 3) % 2
        s.blit(spr.get(), (190, 123 + bob))
        s.blit(spr.get(scale=3), (226, 91 + bob * 3))
        s.blit(spr.get(flip=True), (210, 123 + bob))
        text(s, "LMB DRAW  RMB ERASE  [ ] COLOR", W // 2, 161, GRAY, 1, "center")
        text(s, "C CLEAR  R RESET  F FLIP  ARROWS SHIFT", W // 2, 167, GRAY, 1, "center")
        text(s, "ESC: SAVE AND EXIT", W // 2, 173, GREEN, 1, "center")


# ------------------------------------------------------------ shared battle bits
def countdown_step(g, pt, dt):
    new = pt + dt
    for mark, snd in ((0.0, "beep"), (0.5, "beep"), (1.0, "beep"), (1.5, "go")):
        if pt < mark <= new:
            g.play(snd)
    return new


def draw_countdown(s, pt):
    if pt < 1.5:
        lab = "3" if pt < 0.5 else "2" if pt < 1.0 else "1"
        text(s, lab, W // 2, 70, CREAM, 8, "center", BLACK)
    else:
        text(s, "FIGHT!", W // 2, 72, YELLOW, 5, "center", RED)


def draw_pause(s, sel):
    shade(s, (0, 0, W, H), 150)
    panel(s, 100, 58, 120, 62, NAVY, CREAM)
    text(s, "PAUSED", W // 2, 64, YELLOW, 2, "center")
    for i, it in enumerate(("RESUME", "RESTART", "QUIT TO MENU")):
        text(s, ("> " + it + " <") if i == sel else it, W // 2, 84 + i * 11, YELLOW if i == sel else CREAM, 1, "center")


def pause_input(scene, k, restart, quit_to):
    g = scene.g
    if k in (pygame.K_ESCAPE, pygame.K_p):
        scene.paused = False
    elif k in KEY_UP:
        scene.psel = (scene.psel - 1) % 3
        g.play("select")
    elif k in KEY_DOWN:
        scene.psel = (scene.psel + 1) % 3
        g.play("select")
    elif k in KEY_ENTER or k == pygame.K_SPACE:
        g.play("confirm")
        if scene.psel == 0:
            scene.paused = False
        elif scene.psel == 1:
            restart()
        else:
            quit_to()


HERO_X = 56
ENEMY_CX = 252


class Battle(Scene):
    def __init__(self, g, level):
        super().__init__(g)
        self.level = level
        self.cfg = cfg = level_config(level, SETTINGS["difficulty"])
        up = g.save["upgrades"]
        self.max_hp = g.max_hearts()
        self.hp = clamp(g.run_hp, 1, self.max_hp)
        self.start_hp, self.start_score = self.hp, g.run_score
        self.dmg_base = 1 + up.get("power", 0)
        self.bar = TimingBar(W // 2 - BAR_W // 2)
        self.bar.set_speed(cfg["speed"] * (1 - 0.05 * up.get("slow", 0)))
        self.bar.zone_h = cfg["zone"] + 2 * up.get("focus", 0)
        self.bar.drift = cfg["drift"]
        self.bar.erratic = cfg["erratic"]
        self.bar.n_danger = cfg["danger"]
        self.bar.new_target()
        self.bar.cursor = random.uniform(0, BAR_H)
        self.interval = cfg["interval"] * (1 + 0.06 * up.get("armor", 0))
        self.enemy = g.assets.monster(cfg)
        self.esize = cfg["size"]
        self.ehp = self.emax = cfg["hp"]
        self.atk = 0.0
        self.phase, self.pt = "ready", -0.01
        self.combo = self.best_combo = self.score = self.taken = 0
        self.enraged = False
        self.fx, self.amb, self.t = FX(), Ambient(cfg["world"]), 0.0
        self.hero_lunge = self.hero_hurt = self.enemy_hurt = self.enemy_lunge = 0.0
        self.hitstop = 0.0
        self.paused, self.psel = False, 0
        self.reward = self.stars = self.bonus = 0

    # ---- input
    def pause(self):
        if self.phase in ("ready", "fight"):
            self.paused, self.psel = True, 0

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        g, k = self.g, e.key
        if self.paused:
            pause_input(self, k, self.restart, lambda: g.go(TitleScene(g)))
            return
        if self.phase in ("ready", "fight"):
            if k in (pygame.K_ESCAPE, pygame.K_p):
                self.pause()
            elif self.phase == "fight" and k in (pygame.K_SPACE, pygame.K_a, pygame.K_RETURN):
                self.strike()
        elif self.phase in ("victory", "defeat") and self.pt > 0.4:
            if k in KEY_ENTER or k == pygame.K_SPACE:
                if self.phase == "victory":
                    g.go(Battle(g, self.level + 1))
                else:
                    g.run_hp, g.run_score = g.max_hearts(), self.start_score
                    g.go(Battle(g, self.level))
            elif k == pygame.K_u:
                lv = self.level
                nxt = (lambda: Battle(g, lv + 1)) if self.phase == "victory" else (lambda: Battle(g, lv))
                if self.phase == "defeat":
                    g.run_hp, g.run_score = g.max_hearts(), self.start_score
                g.go(ShopScene(g, nxt))
            elif k == pygame.K_ESCAPE:
                g.play("back")
                g.go(TitleScene(g))

    def restart(self):
        g = self.g
        g.run_hp, g.run_score = self.start_hp, self.start_score
        g.go(Battle(g, self.level))

    # ---- game logic
    def strike(self):
        g = self.g
        res = self.bar.strike()
        if res is None:
            g.play("deny")
            return
        ey = GROUND_Y - self.esize // 2
        if res in ("hit", "perfect"):
            perfect = res == "perfect"
            dmg = (self.dmg_base + self.combo // 5) * (2 if perfect else 1)
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
            self.score += 10 * (1 + self.combo // 3) * (2 if perfect else 1)
            self.ehp = max(0, self.ehp - dmg)
            self.bar.speed = min(self.bar.base_speed * 1.35, self.bar.speed * 1.025)
            self.bar.new_target()
            self.bar.mark(GREEN)
            self.hero_lunge, self.enemy_hurt = 0.2, 0.12
            self.hitstop = 0.09 if perfect else 0.05
            self.fx.slash(ENEMY_CX, ey)
            self.fx.burst(ENEMY_CX, ey, YELLOW if perfect else CREAM, 14 if perfect else 8)
            self.fx.text(ENEMY_CX, ey - self.esize // 2 - 14, "-%d" % dmg, YELLOW if perfect else CREAM, 2)
            if perfect:
                self.fx.text(W // 2, BAR_Y - 6, "PERFECT!", YELLOW, 1, 0.7)
                self.atk = max(0.0, self.atk - 0.9)
                self.g.add_shake(0.12)
            g.play("crit" if perfect else "hit")
            if self.combo >= 3 and self.combo % 5 == 0:
                self.fx.text(HERO_X + 8, GROUND_Y - 30, "COMBO X%d" % self.combo, ORANGE, 1, 0.9)
            if self.cfg["boss"] and not self.enraged and self.ehp <= self.emax // 2 and self.ehp > 0:
                self.enraged = True
                self.interval *= 0.8
                self.bar.base_speed *= 1.1
                self.bar.speed *= 1.1
                self.bar.n_danger = min(3, self.bar.n_danger + 1)
                self.bar.new_target()
                self.fx.text(ENEMY_CX, 40, "ENRAGED!", RED, 2, 1.4)
                g.add_shake(0.3)
            if self.ehp <= 0:
                self.phase, self.pt = "dying", 0.0
                g.play("ko")
                g.add_shake(0.35)
        else:
            self.combo = 0
            self.bar.freeze = 2.0 if SETTINGS["hardcore"] else 1.0
            self.bar.mark(RED)
            self.fx.text(W // 2, BAR_Y + BAR_H // 2, "MISS", RED, 1, 0.7)
            g.play("miss")
            if res == "danger":
                self.fx.text(W // 2, BAR_Y + 12, "TRAP!", RED, 1, 0.8)
                self.hurt_hero(1)

    def hurt_hero(self, n):
        self.hp -= n
        self.taken += n
        self.hero_hurt = 0.4
        self.g.play("hurt")
        self.g.add_shake(0.25)
        self.fx.burst(HERO_X + 8, GROUND_Y - 8, RED, 10)
        self.fx.text(HERO_X + 8, GROUND_Y - 26, "-%d" % n, RED, 2)
        if self.hp <= 0:
            self.hp = 0
            self.phase, self.pt = "hero_dying", 0.0
            self.g.play("lose")

    def finish_win(self):
        g, lv = self.g, self.level
        up = g.save["upgrades"]
        self.reward = int((3 + lv) * (3 if self.cfg["boss"] else 1) * (1 + 0.2 * up.get("greed", 0)))
        self.stars = 3 if self.taken == 0 else (2 if self.taken <= 2 else 1)
        self.bonus = 50 * lv + 100 * self.hp
        g.run_score += self.score + self.bonus
        g.run_hp = min(self.max_hp, self.hp + (self.max_hp if self.cfg["boss"] else 1))
        g.save["coins"] += self.reward
        g.save["highest"] = max(g.save["highest"], lv + 1)
        g.save["stars"][str(lv)] = max(g.save["stars"].get(str(lv), 0), self.stars)
        g.save["best_score"] = max(g.save["best_score"], g.run_score)
        g.save_now()
        self.phase, self.pt = "victory", 0.0
        g.play("win")
        for i in range(14):
            self.fx.burst(random.randint(80, 240), random.randint(30, 90), YELLOW, 3, 40, 40, 1.0, 2)

    def finish_loss(self):
        g = self.g
        frac = 1.0 - self.ehp / self.emax
        self.reward = int((3 + self.level) * 0.5 * frac)
        g.run_score += self.score
        g.save["coins"] += self.reward
        g.save["best_score"] = max(g.save["best_score"], g.run_score)
        g.save_now()
        self.phase, self.pt = "defeat", 0.0

    def enemy_attack(self):
        self.atk = 0.0
        self.enemy_lunge = 0.35
        self.hurt_hero(1)

    # ---- update
    def update(self, dt):
        self.fx.update(dt)
        if self.paused:
            return
        if self.hitstop > 0:
            self.hitstop -= dt
            return
        self.t += dt
        self.amb.update(dt)
        for n in ("hero_lunge", "hero_hurt", "enemy_hurt", "enemy_lunge"):
            if getattr(self, n) > 0:
                setattr(self, n, getattr(self, n) - dt)
        if self.phase == "ready":
            self.bar.update(dt)
            self.pt = countdown_step(self.g, self.pt, dt)
            if self.pt >= 2.0:
                self.phase = "fight"
        elif self.phase == "fight":
            self.bar.update(dt)
            self.atk += dt
            if self.atk >= self.interval:
                self.enemy_attack()
        elif self.phase == "dying":
            self.pt += dt
            if self.pt >= 1.0:
                self.finish_win()
        elif self.phase == "hero_dying":
            self.pt += dt
            if self.pt >= 1.0:
                self.finish_loss()
        else:
            self.pt += dt

    # ---- drawing
    def draw_enemy(self, s):
        sz = self.esize
        if self.phase == "dying":
            if self.pt > 0.7 or int(self.pt * 16) % 2:
                return
        off = 0
        if self.enemy_lunge > 0:
            off = -int(math.sin((1 - self.enemy_lunge / 0.35) * math.pi) * 34)
        warn = self.phase == "fight" and self.interval - self.atk < 0.9
        jit = (int(self.t * 30) % 3 - 1) if warn else 0
        bob = int(self.t * 2.5) % 2
        x = ENEMY_CX - sz // 2 + off + jit
        shade(s, (ENEMY_CX - sz // 2 + 1, GROUND_Y - 1, sz - 2, 3), 100)
        tint = CREAM if self.enemy_hurt > 0 or self.phase == "dying" else None
        s.blit(self.enemy.get(tint=tint), (x, GROUND_Y - sz - bob))
        if warn and int(self.t * 10) % 2:
            text(s, "!", ENEMY_CX, GROUND_Y - sz - 30, RED, 3, "center", BLACK)

    def draw_hero(self, s):
        if self.phase == "hero_dying" and (self.pt > 0.7 or int(self.pt * 16) % 2):
            return
        off = int(math.sin((1 - self.hero_lunge / 0.2) * math.pi) * 44) if self.hero_lunge > 0 else 0
        tint = None
        if self.hero_hurt > 0 or self.phase == "hero_dying":
            tint = RED if int(self.t * 20) % 2 else CREAM
        bob = int(self.t * 3) % 2 if self.phase != "hero_dying" else 0
        shade(s, (HERO_X + 2, GROUND_Y - 1, 12, 3), 100)
        s.blit(self.g.assets.hero.get(tint=tint), (HERO_X + off - (3 if self.hero_hurt > 0 else 0), GROUND_Y - 16 - bob))

    def draw(self, s):
        g, cfg = self.g, self.cfg
        s.blit(g.assets.background(cfg["world"]), (0, 0))
        self.amb.draw(s)
        self.draw_enemy(s)
        self.draw_hero(s)
        self.bar.draw(s, RED if cfg["boss"] else CYAN)
        self.fx.draw(s)
        # HUD
        draw_hearts(s, g, 6, 6, self.hp, self.max_hp)
        text(s, "LV %d  %s" % (self.level, cfg["name"]), W // 2, 6, YELLOW, 1, "center", BLACK)
        text(s, WORLD_NAMES[cfg["world"]], W // 2, 14, GRAY, 1, "center")
        text(s, "SCORE %d" % (g.run_score + self.score), W - 6, 6, CREAM, 1, "right", BLACK)
        s.blit(g.assets.icon["coin"].get(), (W - 6 - text_w(str(g.save["coins"])) - 7, 14))
        text(s, str(g.save["coins"]), W - 6, 15, YELLOW, 1, "right", BLACK)
        if cfg["boss"] and int(self.t * 2) % 2 == 0:
            text(s, "BOSS", W // 2, 22, RED, 1, "center")
        # enemy bars
        bx, by = ENEMY_CX - 28, GROUND_Y - self.esize - 14
        s.fill(BLACK, (bx - 1, by - 1, 58, 7))
        s.fill(PLUM, (bx, by, 56, 5))
        if self.ehp > 0:
            s.fill(RED, (bx, by, max(1, 56 * self.ehp // self.emax), 5))
            s.fill(ORANGE, (bx, by, max(1, 56 * self.ehp // self.emax), 1))
        text(s, "%d/%d" % (self.ehp, self.emax), ENEMY_CX, by - 7, CREAM, 1, "center", BLACK)
        ay = GROUND_Y + 8
        text(s, "ATK", bx, ay - 1, GRAY)
        s.fill(BLACK, (bx + 13, ay - 1, 44, 7))
        frac = clamp(self.atk / self.interval, 0, 1)
        col = RED if frac > 0.75 and int(self.t * 8) % 2 else (YELLOW if frac < 0.75 else ORANGE)
        s.fill(PLUM, (bx + 14, ay, 42, 5))
        s.fill(col, (bx + 14, ay, int(42 * frac), 5))
        if self.combo >= 2:
            text(s, "COMBO X%d" % self.combo, HERO_X + 8, GROUND_Y + 8, ORANGE, 1, "center", BLACK)
        text(s, "SPACE/A: STRIKE    P: PAUSE", W // 2, 172, GRAY, 1, "center")
        if self.phase == "ready":
            if self.pt < 1.5:
                text(s, "BOSS BATTLE!" if cfg["boss"] else "LEVEL %d" % self.level, W // 2, 40,
                     RED if cfg["boss"] else CREAM, 2, "center", BLACK)
            draw_countdown(s, self.pt)
        if self.phase in ("victory", "defeat") and self.pt > 0.15:
            self.draw_result(s)
        if self.paused:
            draw_pause(s, self.psel)

    def draw_result(self, s):
        g, win = self.g, self.phase == "victory"
        shade(s, (0, 0, W, H), 120)
        panel(s, 50, 32, 220, 112, NAVY, GREEN if win else RED)
        text(s, "VICTORY!" if win else "DEFEATED", W // 2, 40, GREEN if win else RED, 3, "center", BLACK)
        if win:
            for k in range(3):
                s.blit(g.assets.icon["star" if k < self.stars else "star_empty"].get(scale=2), (W // 2 - 26 + k * 18, 64))
            text(s, "FLAWLESS!" if self.taken == 0 else "HITS TAKEN: %d" % self.taken, W // 2, 82, CYAN, 1, "center")
            text(s, "SCORE +%d" % (self.score + self.bonus), W // 2, 94, CREAM, 1, "center")
            text(s, "BEST COMBO X%d" % self.best_combo, W // 2, 104, GRAY, 1, "center")
            if self.level + 1 > 1:
                text(s, "LEVEL %d UNLOCKED" % (self.level + 1), W // 2, 114, YELLOW, 1, "center")
        else:
            text(s, "ENEMY HP LEFT: %d/%d" % (self.ehp, self.emax), W // 2, 70, CREAM, 1, "center")
            text(s, "SCORE %d" % g.run_score, W // 2, 82, CREAM, 1, "center")
            text(s, "BEST COMBO X%d" % self.best_combo, W // 2, 94, GRAY, 1, "center")
        s.blit(g.assets.icon["coin"].get(), (W // 2 - text_w("+%d COINS" % self.reward) // 2 - 8, 124))
        text(s, "+%d COINS" % self.reward, W // 2, 124, YELLOW, 1, "center")
        text(s, ("ENTER: NEXT" if win else "ENTER: RETRY") + "   U: UPGRADES   ESC: MENU", W // 2, 134, GRAY, 1, "center")


# ------------------------------------------------------------------------ duel
class Fighter:
    def __init__(self, idx, bar, cpu, spr, name):
        self.idx, self.bar, self.cpu, self.spr, self.name = idx, bar, cpu, spr, name
        self.streak = 0
        self.lunge = 0.0
        self.aim = None
        self.prev = None


CPU_SKILL = {"EASY": (0.55, 0.55), "NORMAL": (0.33, 0.75), "HARD": (0.17, 0.92)}
P1_CX, P2_CX = 84, 236


class Duel(Scene):
    KO = 12
    ROUND_TIME = 30.0

    def __init__(self, g, cpu=False, wins=None, rnd=1):
        super().__init__(g)
        self.cpu, self.rnd = cpu, rnd
        self.wins = wins or [0, 0]
        self.best3 = SETTINGS["format"] == "BEST OF 3"
        bars = [TimingBar(24), TimingBar(W - 24 - BAR_W)]
        for b in bars:
            b.set_speed(90)
            b.zone_h = 24
            b.new_target()
            b.cursor = random.uniform(0, BAR_H)
        self.f = [Fighter(0, bars[0], False, g.assets.hero, "P1"),
                  Fighter(1, bars[1], cpu, g.assets.rival, "CPU" if cpu else "P2")]
        self.bal = 0
        self.time_left = self.ROUND_TIME
        self.sudden = False
        self.phase, self.pt = "ready", -0.01
        self.winner, self.label = None, ""
        self.match_over = False
        self.world = (rnd - 1) % 5
        self.amb = Ambient(self.world)
        self.fx = FX()
        self.t = 0.0
        self.paused, self.psel = False, 0

    def pause(self):
        if self.phase in ("ready", "fight"):
            self.paused, self.psel = True, 0

    def handle(self, e):
        if e.type != pygame.KEYDOWN:
            return
        g, k = self.g, e.key
        if self.paused:
            pause_input(self, k, lambda: g.go(Duel(g, self.cpu)), lambda: g.go(TitleScene(g)))
            return
        if self.phase in ("ready", "fight"):
            if k in (pygame.K_ESCAPE, pygame.K_p):
                self.pause()
            elif self.phase == "fight":
                if k == pygame.K_a or (self.cpu and k == pygame.K_SPACE):
                    self.strike(self.f[0])
                elif k == pygame.K_l and not self.cpu:
                    self.strike(self.f[1])
        elif self.phase == "over" and self.pt > 0.4:
            if k in KEY_ENTER or k == pygame.K_SPACE:
                if self.match_over:
                    g.go(Duel(g, self.cpu))
                else:
                    g.go(Duel(g, self.cpu, self.wins, self.rnd + 1))
            elif k == pygame.K_ESCAPE:
                g.play("back")
                g.go(TitleScene(g))

    def clash_x(self):
        return 160 + self.bal * (56.0 / self.KO)

    def strike(self, f):
        g = self.g
        res = f.bar.strike()
        if res is None:
            g.play("deny")
            return
        cx = self.clash_x()
        f.aim = f.prev = None
        if res in ("hit", "perfect"):
            perfect = res == "perfect"
            f.streak += 1
            power = 1 + f.streak // 3 + (1 if perfect else 0)
            self.bal = clamp(self.bal + (power if f.idx == 0 else -power), -self.KO, self.KO)
            f.bar.speed = min(190.0, f.bar.speed + 5)
            f.bar.new_target()
            f.bar.mark(GREEN)
            f.lunge = 0.2
            col = CYAN if f.idx == 0 else ORANGE
            self.fx.burst(cx, GROUND_Y - 10, col, 12 if perfect else 7, 60)
            bx = f.bar.x + BAR_W // 2
            self.fx.text(bx, BAR_Y - 8, "+%d" % power, YELLOW if perfect else CREAM, 1, 0.7)
            g.play("crit" if perfect else "hit")
            if perfect or f.streak % 3 == 0:
                g.add_shake(0.1)
            if abs(self.bal) >= self.KO:
                self.end_round(0 if self.bal > 0 else 1, "K.O.!")
            elif self.sudden and self.bal != 0:
                self.end_round(0 if self.bal > 0 else 1, "SUDDEN DEATH!")
        else:
            f.streak = 0
            f.bar.freeze = 2.0 if SETTINGS["hardcore"] else 1.0
            f.bar.mark(RED)
            self.fx.text(f.bar.x + BAR_W // 2, BAR_Y - 8, "MISS", RED, 1, 0.7)
            g.play("miss")

    def end_round(self, winner, label):
        self.phase, self.pt = "ko", 0.0
        self.winner, self.label = winner, label
        if winner is not None:
            self.wins[winner] += 1
        self.match_over = (not self.best3) or max(self.wins) >= 2
        self.g.play("ko")
        self.g.add_shake(0.4)
        cx = self.clash_x()
        self.fx.burst(cx, GROUND_Y - 10, YELLOW, 30, 110, 40, 0.8, 2)

    def cpu_act(self, f):
        b = f.bar
        if b.freeze > 0:
            f.aim = f.prev = None
            return
        sigma, prob = CPU_SKILL[SETTINGS["difficulty"]]
        zy, zh = b.zone()
        if f.aim is None:
            f.aim = zy + zh / 2 + random.gauss(0, sigma * zh)
            f.prev = None
        rel = b.cursor - f.aim
        crossed = f.prev is not None and f.prev * rel <= 0 and f.prev != rel
        f.prev = rel
        if crossed:
            if random.random() < prob:
                self.strike(f)
            else:
                f.aim = None

    def update(self, dt):
        self.fx.update(dt)
        if self.paused:
            return
        self.t += dt
        self.amb.update(dt)
        for f in self.f:
            f.lunge = max(0.0, f.lunge - dt)
        if self.phase == "ready":
            for f in self.f:
                f.bar.update(dt)
            self.pt = countdown_step(self.g, self.pt, dt)
            if self.pt >= 2.0:
                self.phase = "fight"
        elif self.phase == "fight":
            for f in self.f:
                f.bar.update(dt)
            for f in self.f:
                if f.cpu and self.phase == "fight":
                    self.cpu_act(f)
            if self.phase == "fight" and not self.sudden:
                self.time_left -= dt
                if self.time_left <= 0:
                    self.time_left = 0
                    if self.bal != 0:
                        self.end_round(0 if self.bal > 0 else 1, "TIME!")
                    else:
                        self.sudden = True
                        self.fx.text(W // 2, 60, "SUDDEN DEATH!", RED, 2, 1.6)
                        self.g.play("deny")
        elif self.phase == "ko":
            self.pt += dt
            if self.pt >= 1.6:
                self.phase, self.pt = "over", 0.0
        else:
            self.pt += dt

    def draw_beam(self, s, x0, x1, cols, flip):
        if x1 <= x0:
            return
        y = GROUND_Y - 13
        s.fill(cols[0], (x0, y, x1 - x0, 6))
        s.fill(cols[1], (x0, y + 1, x1 - x0, 4))
        s.fill(cols[2], (x0, y + 2, x1 - x0, 2))
        off = int(self.t * 90) % 12
        for x in range(x0 - 12 + (off if not flip else 12 - off), x1, 12):
            a, b = max(x, x0), min(x + 4, x1)
            if b > a:
                s.fill(cols[0], (a, y + 2, b - a, 2))

    def draw_fighter(self, s, f, cx):
        sign = 1 if f.idx == 0 else -1
        off = int(math.sin((1 - f.lunge / 0.2) * math.pi) * 6) * sign if f.lunge > 0 else 0
        tint, bob, up = None, int(self.t * 3) % 2, 0
        if self.phase in ("ko", "over") and self.winner is not None:
            if f.idx != self.winner:
                off = -sign * int(min(self.pt, 1.2) * 70)
                tint = RED if int(self.t * 20) % 2 else CREAM
                bob = 0
            else:
                up = int(abs(math.sin(self.pt * 8)) * 6)
        shade(s, (cx - 6 + off, GROUND_Y - 1, 12, 3), 100)
        s.blit(f.spr.get(flip=(f.idx == 1), tint=tint), (cx - 8 + off, GROUND_Y - 16 - bob - up))

    def draw(self, s):
        g = self.g
        s.blit(g.assets.background(self.world), (0, 0))
        self.amb.draw(s)
        self.draw_fighter(s, self.f[0], P1_CX)
        self.draw_fighter(s, self.f[1], P2_CX)
        cx = int(self.clash_x())
        self.draw_beam(s, P1_CX + 10, cx, (BLUE, CYAN, CREAM), False)
        self.draw_beam(s, cx, P2_CX - 10, (RED, ORANGE, YELLOW), True)
        r = 6 + int(math.sin(self.t * 30) * 1.5)
        pygame.draw.circle(s, YELLOW, (cx, GROUND_Y - 10), r)
        pygame.draw.circle(s, CREAM, (cx, GROUND_Y - 10), max(2, r - 3))
        self.f[0].bar.draw(s, CYAN)
        self.f[1].bar.draw(s, ORANGE)
        self.fx.draw(s)
        # HUD: tug meter
        mx, my, mw = 80, 20, 160
        s.fill(BLACK, (mx - 2, my - 2, mw + 4, 10))
        frac = (self.bal + self.KO) / (2.0 * self.KO)
        split = int(mw * frac)
        s.fill(CYAN, (mx, my, split, 6))
        s.fill(RED, (mx + split, my, mw - split, 6))
        s.fill(CREAM, (mx + split - 1, my - 2, 2, 10))
        s.fill(BLACK, (mx + mw // 2, my, 1, 6))
        secs = "SUDDEN DEATH" if self.sudden else str(int(math.ceil(self.time_left)))
        text(s, secs, W // 2, 4, RED if (self.sudden or self.time_left < 5) else CREAM, 2 if not self.sudden else 1, "center", BLACK)
        text(s, "P1", 8, 4, CYAN, 2, "left", BLACK)
        text(s, self.f[1].name, W - 8, 4, ORANGE, 2, "right", BLACK)
        if self.best3:
            for k in range(2):
                s.fill(YELLOW if k < self.wins[0] else PLUM, (8 + k * 8, 18, 6, 6))
                s.fill(YELLOW if k < self.wins[1] else PLUM, (W - 14 - k * 8, 18, 6, 6))
            text(s, "ROUND %d" % self.rnd, W // 2, 30, GRAY, 1, "center")
        for f, key in ((self.f[0], "[A]"), (self.f[1], "[L]" if not self.cpu else "CPU")):
            cxb = f.bar.x + BAR_W // 2
            if f.streak >= 2:
                text(s, "STREAK X%d" % f.streak, cxb, GROUND_Y + 8, ORANGE, 1, "center", BLACK)
            text(s, key, cxb, GROUND_Y + 18, GRAY, 1, "center")
        if self.phase == "ready":
            draw_countdown(s, self.pt)
        if self.phase in ("ko", "over"):
            if self.pt < 1.6 or self.phase == "ko":
                text(s, self.label, W // 2, 60, YELLOW, 5, "center", RED)
        if self.phase == "over" and self.pt > 0.15:
            self.draw_result(s)
        if self.paused:
            draw_pause(s, self.psel)

    def draw_result(self, s):
        shade(s, (0, 0, W, H), 120)
        panel(s, 50, 42, 220, 92, NAVY, YELLOW)
        w = self.winner
        if w is None:
            head, col = "DRAW!", CREAM
        else:
            nm = self.f[w].name
            head = ("%s WINS THE MATCH!" if (self.match_over and self.best3) else "%s WINS!") % nm
            col = CYAN if w == 0 else ORANGE
        text(s, head, W // 2, 50, col, 2, "center", BLACK)
        if self.best3:
            text(s, "SCORE  %d - %d" % (self.wins[0], self.wins[1]), W // 2, 74, CREAM, 2, "center")
        else:
            text(s, "FINAL PUSH %+d" % self.bal, W // 2, 76, CREAM, 1, "center")
        hint = "ENTER: REMATCH" if self.match_over else "ENTER: NEXT ROUND"
        text(s, hint, W // 2, 104, YELLOW, 1, "center")
        text(s, "ESC: MENU", W // 2, 116, GRAY, 1, "center")


# ------------------------------------------------------------------------ game
class Game:
    def __init__(self):
        pygame.init()
        self.fullscreen = False
        self.window = pygame.display.set_mode((W * START_SCALE, H * START_SCALE), pygame.RESIZABLE)
        pygame.display.set_caption("Timing Clash")
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.save = load_save()
        self.assets = Assets(self.save["hero"])
        try:
            pygame.display.set_icon(self.assets.hero.get(scale=2))
        except Exception:
            pass
        self.audio = Audio()
        self.run_hp, self.run_score = self.max_hearts(), 0
        self.shake, self.view, self._scan = 0.0, (0, 0, START_SCALE), None
        self.scene = TitleScene(self)

    # services used by scenes
    def play(self, name):
        self.audio.play(name)

    def go(self, scene):
        self.scene = scene

    def max_hearts(self):
        return 5 + self.save["upgrades"].get("vitality", 0)

    def save_now(self):
        write_save(self.save)

    def add_shake(self, t):
        self.shake = max(self.shake, t)

    def mouse_pos(self):
        mx, my = pygame.mouse.get_pos()
        ox, oy, sc = self.view
        return (mx - ox) // sc, (my - oy) // sc

    def start_run(self, level):
        self.run_hp, self.run_score = self.max_hearts(), 0
        self.go(Battle(self, level))

    def reset_progress(self):
        self.save = {"highest": 1, "coins": 0, "best_score": 0, "upgrades": {}, "stars": {}, "hero": None}
        self.assets.set_hero(None)
        self.run_hp, self.run_score = self.max_hearts(), 0
        self.save_now()

    def quit(self):
        self.save_now()
        pygame.quit()
        sys.exit()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode((W * START_SCALE, H * START_SCALE), pygame.RESIZABLE)

    def present(self):
        win = pygame.display.get_surface()
        ww, wh = win.get_size()
        sc = max(1, min(ww // W, wh // H))
        vw, vh = W * sc, H * sc
        ox, oy = (ww - vw) // 2, (wh - vh) // 2
        self.view = (ox, oy, sc)
        win.fill(BLACK)
        sx = sy = 0
        if self.shake > 0 and SETTINGS["shake"]:
            sx, sy = random.randint(-2, 2) * sc, random.randint(-2, 2) * sc
        win.blit(pygame.transform.scale(self.canvas, (vw, vh)), (ox + sx, oy + sy))
        if SETTINGS["scanlines"] and sc >= 2:
            if self._scan is None or self._scan[0] != (vw, vh):
                sl = pygame.Surface((vw, vh), pygame.SRCALPHA)
                for y in range(sc - 1, vh, sc):
                    sl.fill((0, 0, 0, 55), (0, y, vw, 1))
                self._scan = ((vw, vh), sl)
            win.blit(self._scan[1], (ox, oy))
        pygame.display.flip()

    def run(self):
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", -1)
        while True:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.quit()
                elif e.type == focus_lost:
                    if hasattr(self.scene, "pause"):
                        self.scene.pause()
                elif e.type == pygame.KEYDOWN and (
                        e.key == pygame.K_F11 or (e.key in KEY_ENTER and e.mod & pygame.KMOD_ALT)):
                    self.toggle_fullscreen()
                else:
                    self.scene.handle(e)
            if self.shake > 0:
                self.shake -= dt
            scene = self.scene
            scene.update(dt)
            scene.draw(self.canvas)
            if SETTINGS["fps"]:
                text(self.canvas, "FPS %d" % self.clock.get_fps(), 4, 172, GREEN, 1, "left", BLACK)
            self.present()


def main():
    Game().run()


if __name__ == "__main__":
    main()
