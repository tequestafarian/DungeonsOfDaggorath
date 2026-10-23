"""Top-down Dungeons of Daggorath mockups for a 512K CoCo 3.

Uses a real level: the maze, creature positions and holes/ladders come
from a RAM dump of the running game (tools/level1_ram.hex) and the ROM.

Screen: GIME 320x200x16.  Playfield 320x168 (16x16 cells), HUD 320x32
below it with its own palette (one raster split).

usage: python -I tools/topdown/render_topdown.py [outdir]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from PIL import Image  # noqa: E402
from dodrom import Rom, CREATURES, glyph, text_codes  # noqa: E402
import sprites as SP  # noqa: E402

W, H = 320, 200
PF_H = 168                     # playfield height
CELL = 24


def rgb2(r, g, b):
    return (r * 85, g * 85, b * 85)


KEYS = "kndstmbgyrelvcow"
PAL = [rgb2(0, 0, 0), rgb2(0, 0, 1), rgb2(1, 1, 1), rgb2(2, 2, 2),
       rgb2(1, 1, 2), rgb2(1, 0, 0), rgb2(2, 1, 0), rgb2(3, 2, 0),
       rgb2(3, 3, 2), rgb2(3, 0, 0), rgb2(0, 2, 0), rgb2(1, 3, 1),
       rgb2(2, 0, 3), rgb2(0, 3, 3), rgb2(3, 1, 0), rgb2(3, 3, 3)]
# HUD band palette (raster split): same slots, panel tones swapped in
HUD_PAL = list(PAL)
HUD_PAL[1] = rgb2(1, 0, 1)     # panel plum
HUD_PAL[4] = rgb2(2, 1, 2)     # panel edge
K = {ch: i for i, ch in enumerate(KEYS)}

# one darkening step per palette slot (towards black)
DARKER = {K[a]: K[b] for a, b in [
    ("k", "k"), ("n", "k"), ("d", "n"), ("s", "d"), ("t", "n"), ("m", "k"),
    ("b", "m"), ("g", "b"), ("y", "g"), ("r", "m"), ("e", "n"), ("l", "e"),
    ("v", "n"), ("c", "t"), ("o", "b"), ("w", "s")]}

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]
PAS, DOR, SDR, WAL = 0, 1, 2, 3


def hash01(*k):
    h = 2166136261
    for v in k:
        h = ((h ^ (v & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5bd1e995) & 0xFFFFFFFF
    h ^= h >> 15
    return (h & 0xFFFF) / 65536.0


# ---- level data ----------------------------------------------------------
class Level:
    def __init__(self, rom, dump_path):
        b = bytes(int(x, 16) for x in open(dump_path).read().split())
        base = 0x0200

        def rd(addr, n=1):
            return b[addr - base:addr - base + n]
        self.maze = rd(rom.addr("MAZLND"), 1024)
        self.player = tuple(rd(rom.addr("PROW"), 2))
        self.level = rd(rom.addr("LEVEL"))[0]
        self.creatures = {}
        ccb, clen = rom.addr("CCBLND"), rom.sym["CC.LEN"]
        for i in range(32):
            e = rd(ccb + i * clen, clen)
            if e[rom.sym["P.CCUSE"]]:
                pos = (e[rom.sym["P.CCROW"]], e[rom.sym["P.CCCOL"]])
                self.creatures[pos] = CREATURES[e[rom.sym["P.CCTYP"]]]
        # VFTTAB: per level, an "up" list then a "down" list, each ended by -128
        t = rom.addr("VFTTAB")
        lists, cur, a = [], [], t
        while len(lists) < self.level + 2:
            v = rom.byte(a)
            if v >= 0x80:
                lists.append(cur)
                cur = []
                a += 1
                continue
            cur.append((v, rom.byte(a + 1), rom.byte(a + 2)))
            a += 3
        # lists split on -128: level L's "up" list is level L-1's "down" list
        up, down = lists[self.level], lists[self.level + 1]
        self.vert = {}
        for code, r, c in up:
            self.vert[(r, c)] = "ladder_up" if code == 1 else "hole_up"
        for code, r, c in down:
            self.vert[(r, c)] = "ladder_dn" if code == 1 else "hole_dn"

    def cell(self, r, c):
        if not (0 <= r < 32 and 0 <= c < 32):
            return 0xFF
        return self.maze[r * 32 + c]

    def is_rock(self, r, c):
        return self.cell(r, c) == 0xFF

    def side(self, r, c, d):
        v = self.cell(r, c)
        if v == 0xFF:
            return WAL
        return (v >> (2 * d)) & 3


# ---- frame buffer --------------------------------------------------------
class Frame:
    def __init__(self):
        self.px = [[0] * W for _ in range(H)]

    def put(self, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = c

    def image(self):
        img = Image.new("RGB", (W, H))
        p = img.load()
        for y in range(H):
            pal = HUD_PAL if y >= PF_H else PAL
            for x in range(W):
                p[x, y] = pal[self.px[y][x]]
        return img


def darken(c, steps, x, y):
    """Darken slot c by a fractional number of steps, ordered-dithered."""
    whole = int(steps)
    frac = steps - whole
    if BAYER[y & 3][x & 3] < frac * 16:
        whole += 1
    for _ in range(min(whole, 6)):
        c = DARKER[c]
    return c


# ---- world tiles (drawn into a world bitmap, CELL px per maze square) ------
FACE = 11          # height of a south-facing wall face
RIM = 4            # lit rim on top of a wall


def build_world(lv, reveal_secret=False):
    """Returns (world, memory): the level art, and the 'remembered' version
    (black floor, navy outlines)."""
    WW = 32 * CELL
    world = [[0] * WW for _ in range(WW)]
    memory = [[0] * WW for _ in range(WW)]

    def put(x, y, c):
        if 0 <= x < WW and 0 <= y < WW:
            world[y][x] = c

    def mem(x, y, c):
        if 0 <= x < WW and 0 <= y < WW:
            memory[y][x] = c

    for r in range(32):
        for c in range(32):
            x0, y0 = c * CELL, r * CELL
            if lv.is_rock(r, c):
                draw_rock(lv, put, mem, r, c, x0, y0)
            else:
                draw_floor(lv, put, r, c, x0, y0)
    for r in range(32):
        for c in range(32):
            if lv.is_rock(r, c):
                continue
            x0, y0 = c * CELL, r * CELL
            for d in (1, 2):      # each shared edge once: east, south
                f = lv.side(r, c, d)
                nr, nc = r + DIRS[d][0], c + DIRS[d][1]
                if lv.is_rock(nr, nc):
                    continue
                if f == WAL or (f == SDR and not reveal_secret):
                    draw_thin_wall(put, mem, d, x0, y0)
                elif f == SDR:
                    draw_door(put, mem, r, c, d, x0, y0, secret=True)
                elif f == DOR:
                    draw_door(put, mem, r, c, d, x0, y0)
            if (r, c) in lv.vert:
                draw_vert(put, mem, lv.vert[(r, c)], x0, y0)
    return world, memory


def dith(x, y, tone):
    return BAYER[y & 3][x & 3] < tone * 16


def draw_floor(lv, put, r, c, x0, y0):
    """Bevelled flagstones, 12px, staggered every other course."""
    S = 12
    for y in range(CELL):
        for x in range(CELL):
            wx, wy = x0 + x, y0 + y
            row = wy // S
            sx_off = (S // 2) if row % 2 else 0
            gx, gy = (wx + sx_off) % S, wy % S
            stone = ((wx + sx_off) // S, row)
            h = hash01(*stone, 3)
            if gx == 0 or gy == 0:
                col = K["k"]
            else:
                tone = 0.2 + 0.4 * h
                if gx == 1 or gy == 1:
                    tone += 0.2                            # worn upper edge
                if hash01(wx, wy, 9) < 0.05:
                    tone = 0                               # pits
                col = K["d"] if dith(wx, wy, tone) else K["n"]
            put(wx, wy, col)
    if hash01(r, c, 77) < 0.35:                            # a crack
        x, y = x0 + 4 + int(hash01(r, c, 1) * 14), y0 + 3 + int(hash01(r, c, 2) * 6)
        for i in range(7):
            put(x, y, K["k"])
            x += 1 if hash01(r, c, i) < 0.6 else 0
            y += 1
    # soft shadow cast by walls onto the floor
    for d, (dr, dc) in enumerate(DIRS):
        if lv.is_rock(r + dr, c + dc) or lv.side(r, c, d) == WAL:
            depth = 5 if d in (0, 3) else 2
            for i in range(CELL):
                for k in range(depth):
                    if d == 0:
                        x, y = x0 + i, y0 + k
                    elif d == 2:
                        x, y = x0 + i, y0 + CELL - 1 - k
                    elif d == 1:
                        x, y = x0 + CELL - 1 - k, y0 + i
                    else:
                        x, y = x0 + k, y0 + i
                    if dith(x, y, 0.85 - k * 0.17):
                        put(x, y, K["k"])


def draw_rock(lv, put, mem, r, c, x0, y0):
    """Solid rock: black void, a lit rim where it meets open floor, and a
    brick face on its south side when the square below is open."""
    open_ = [not lv.is_rock(r + dr, c + dc) for dr, dc in DIRS]
    for y in range(CELL):
        for x in range(CELL):
            put(x0 + x, y0 + y, K["k"])
    face_top = CELL - FACE if open_[2] else CELL
    for y in range(face_top):
        for x in range(CELL):
            wx, wy = x0 + x, y0 + y
            dist = min([y if open_[0] else 99,
                        (CELL - 1 - x) if open_[1] else 99,
                        (face_top - 1 - y) if open_[2] else 99,
                        x if open_[3] else 99])
            if dist == 0:
                col = K["s"] if (open_[2] and y == face_top - 1) else K["t"]
                put(wx, wy, col)
                mem(wx, wy, K["n"])
            elif dist < RIM:
                tone = 0.8 - dist * 0.22 + (hash01(wx // 2, wy // 2, 4) - 0.5) * 0.3
                put(wx, wy, K["t"] if dith(wx, wy, tone) else K["n"])
    if open_[2]:
        for y in range(FACE):
            for x in range(CELL):
                wx, wy = x0 + x, y0 + face_top + y
                course = y // 4
                bx = (wx + (6 if course % 2 else 0)) % 12
                if y % 4 == 3 or bx == 0:
                    col = K["k"]
                else:
                    h = hash01((wx + 6 * course) // 12, wy // 4, 11)
                    tone = 0.75 + 0.25 * h - y * 0.055
                    if y % 4 == 0:
                        tone += 0.25
                    col = K["s"] if dith(wx, wy, tone - 0.5) else (
                        K["d"] if dith(wx, wy, tone) else K["n"])
                put(wx, wy, col)
        for x in range(CELL):
            mem(x0 + x, y0 + CELL - 1, K["n"])


def draw_thin_wall(put, mem, d, x0, y0):
    if d == 2:      # low wall on the south edge, with a short face
        for y in range(-3, 5):
            for x in range(CELL):
                wx, wy = x0 + x, y0 + CELL - 1 + y
                if y < 0:
                    col = K["t"] if y > -3 else K["s"]
                elif y == 4:
                    col = K["k"]
                else:
                    col = K["k"] if wx % 12 == 0 else (K["d"] if y < 3 else K["n"])
                put(wx, wy, col)
                if y == 0:
                    mem(wx, wy, K["n"])
    else:           # east edge: wall top seen from above
        for y in range(CELL):
            for x in range(-2, 3):
                wx, wy = x0 + CELL - 1 + x, y0 + y
                col = K["k"] if x in (-2, 2) else (K["s"] if x == -1 else K["t"])
                put(wx, wy, col)
                if x == 0:
                    mem(wx, wy, K["n"])


def draw_door(put, mem, r, c, d, x0, y0, secret=False):
    wood, dark, trim = (K["b"], K["m"], K["g"]) if not secret else (K["v"], K["n"], K["c"])
    if d == 2:      # door standing across the south edge (front view)
        top, bot = y0 + CELL - 6, y0 + CELL + 5
        for wy in range(top - 2, bot + 1):
            for wx in range(x0, x0 + CELL):
                if wy < top:                                  # lintel
                    col = K["s"] if wy == top - 2 else K["t"]
                elif wx < x0 + 3 or wx >= x0 + CELL - 3:      # stone posts
                    col = K["d"] if wx in (x0 + 1, x0 + CELL - 2) else K["k"]
                elif wy == bot:
                    col = K["k"]
                else:
                    plank = (wx - x0) % 4 == 3
                    col = dark if plank else wood
                    if wy in (top + 2, bot - 3):
                        col = K["d"] if not secret else K["c"]  # iron bands
                put(wx, wy, col)
                mem(wx, wy, K["n"] if wy in (top, bot) else K["k"])
        put(x0 + CELL // 2 + 3, top + 5, trim)
        put(x0 + CELL // 2 + 3, top + 6, trim)
    else:           # door in the east edge, seen from above
        left, right = x0 + CELL - 4, x0 + CELL + 3
        for wy in range(y0 + 1, y0 + CELL - 1):
            for wx in range(left, right + 1):
                if wy < y0 + 4 or wy > y0 + CELL - 5:
                    col = K["t"] if wx not in (left, right) else K["k"]
                elif wx in (left, right):
                    col = K["k"]
                else:
                    col = dark if (wy - y0) % 4 == 3 else wood
                put(wx, wy, col)
                if wx == x0 + CELL - 1:
                    mem(wx, wy, K["n"])
        put(x0 + CELL - 1, y0 + CELL // 2, trim)
    if secret:      # shimmer
        for i in range(8):
            if d == 2:
                sx = x0 + 2 + int(hash01(r, c, i) * (CELL - 4))
                sy = y0 + CELL - 8 + int(hash01(c, r, i) * 14)
            else:
                sx = x0 + CELL - 6 + int(hash01(r, c, i) * 10)
                sy = y0 + 2 + int(hash01(c, r, i) * (CELL - 4))
            put(sx, sy, K["w"] if i % 3 == 0 else K["c"])


def draw_vert(put, mem, kind, x0, y0):
    cx, cy = x0 + CELL / 2, y0 + CELL / 2
    if kind.endswith("_dn"):
        for y in range(y0 + 2, y0 + CELL - 1):
            for x in range(x0 + 2, x0 + CELL - 2):
                e = ((x + 0.5 - cx) / 9.5) ** 2 + ((y + 0.5 - cy) / 8) ** 2
                if e <= 1:
                    col = K["k"]
                    if e > 0.78:
                        col = K["s"] if y > cy else K["d"]     # far lip lit
                    elif e > 0.55 and y < cy:
                        col = K["n"]                           # inner wall
                    put(x, y, col)
                    mem(x, y, K["n"] if e > 0.78 else K["k"])
        if kind == "ladder_dn":
            for y in range(y0 + 5, y0 + CELL - 4):
                put(x0 + 8, y, K["b"])
                put(x0 + 15, y, K["b"])
                if (y - y0) % 4 == 1:
                    for x in range(x0 + 9, x0 + 15):
                        put(x, y, K["g"] if y < cy else K["m"])
    else:   # opening in the ceiling: a shaft of light
        for y in range(y0, y0 + CELL):
            for x in range(x0, x0 + CELL):
                if abs(x - cx) + abs(y - cy) < 10 and dith(x, y, 0.3):
                    put(x, y, K["t"])
        if kind == "ladder_up":
            for y in range(y0 + 1, y0 + CELL - 1):
                put(x0 + 7, y, K["g"])
                put(x0 + 16, y, K["g"])
                if (y - y0) % 4 == 0:
                    for x in range(x0 + 8, x0 + 16):
                        put(x, y, K["b"])


# ---- lighting --------------------------------------------------------------
def visible_cells(lv, origin, max_d=9):
    """Cells the hero can see: line of sight through open edges.

    Doors and walls block sight (the 3-D viewer stops at doors too)."""
    seen = {origin}
    pr, pc = origin
    for r in range(pr - max_d, pr + max_d + 1):
        for c in range(pc - max_d, pc + max_d + 1):
            if (r, c) in seen:
                continue
            if los(lv, origin, (r, c)):
                seen.add((r, c))
    return seen


def los(lv, a, b):
    (r0, c0), (r1, c1) = a, b
    steps = max(abs(r1 - r0), abs(c1 - c0)) * 4
    if steps == 0:
        return True
    pr, pc = r0, c0
    for i in range(1, steps + 1):
        t = i / steps
        fr = r0 + (r1 - r0) * t
        fc = c0 + (c1 - c0) * t
        rr, cc = int(round(fr)), int(round(fc))
        if (rr, cc) != (pr, pc):
            # crossing from (pr,pc) to (rr,cc): must pass an open edge
            if lv.is_rock(pr, pc):
                return False
            dr, dc = rr - pr, cc - pc
            if dr and dc:
                # diagonal step: allow if either L-path is open
                ok = False
                for mid in ((pr + dr, pc), (pr, pc + dc)):
                    if step_open(lv, (pr, pc), mid) and step_open(lv, mid, (rr, cc)):
                        ok = True
                if not ok:
                    return (rr, cc) == (r1, c1) and lv.is_rock(rr, cc) and \
                        (step_open(lv, (pr, pc), (pr + dr, pc)) or step_open(lv, (pr, pc), (pr, pc + dc)))
            elif not step_open(lv, (pr, pc), (rr, cc)):
                # the blocking wall itself is visible
                return (rr, cc) == (r1, c1) and lv.is_rock(rr, cc)
            pr, pc = rr, cc
    return True


def step_open(lv, a, b):
    if lv.is_rock(*a):
        return False
    d = DIRS.index((b[0] - a[0], b[1] - a[1]))
    if lv.is_rock(*b):
        return False
    return lv.side(a[0], a[1], d) == PAS


def light_at(light, dist):
    """Continuous SETFAX: full until light-7, black by 'light'."""
    v = (light - dist) / 7.0
    return max(0.0, min(1.0, v))


# ---- compositing -------------------------------------------------------------
def blit_sprite(f, art, x, y, cam, lum_fn, flash=None, shadow=True):
    rows = SP.parse(art)
    h, w = len(rows), len(rows[0])
    if shadow:
        cx, cy = x + w // 2, y + h - 1
        for sy in range(-2, 2):
            for sx in range(-6, 7):
                if (sx / 6.5) ** 2 + (sy / 2.2) ** 2 <= 1:
                    X, Y = cx + sx - cam[0], cy + sy - cam[1]
                    if 0 <= Y < PF_H and BAYER[Y & 3][X & 3] < 10:
                        f.put(X, Y, K["k"])
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            X, Y = x + i - cam[0], y + j - cam[1]
            if not (0 <= Y < PF_H):
                continue
            c = K[ch]
            if flash and ch != "k":
                c = K[flash]
            steps = lum_fn(x + i, y + j)
            f.put(X, Y, darken(c, steps, X, Y))


def render_view(lv, world, hero, facing, light, explored, actors, items=(),
                effects=None, mlight=0, glow=None):
    f = Frame()
    world, memory = world
    half = CELL // 2
    cam = (hero[1] * CELL + half - W // 2, hero[0] * CELL + half - PF_H // 2)
    seen = visible_cells(lv, hero)
    hx, hy = hero[1] * CELL + half, hero[0] * CELL + half

    def lum_steps(wx, wy):
        cell = (wy // CELL, wx // CELL)
        if cell not in seen:
            return 6
        d = math.hypot(wx - hx, wy - hy) / CELL
        lit = light_at(light, d)
        if glow:
            gx, gy, gl = glow
            lit = max(lit, light_at(gl, math.hypot(wx - gx, wy - gy) / CELL) * 0.9)
        return (1 - lit) * 4.5

    for y in range(PF_H):
        for x in range(W):
            wx, wy = x + cam[0], y + cam[1]
            if not (0 <= wx < 32 * CELL and 0 <= wy < 32 * CELL):
                continue
            cell = (wy // CELL, wx // CELL)
            c = world[wy][wx]
            if cell in seen:
                c = darken(c, lum_steps(wx, wy), x, y)
                d = math.hypot(wx - hx, wy - hy) / CELL
                if c == K["n"] and dith(x, y, 0.4 - d * 0.22):
                    c = K["m"]                      # warm torch light in the shadows
            elif cell in explored:
                c = memory[wy][wx]          # remembered: navy outlines only
            else:
                c = K["k"]
            f.px[y][x] = c

    def sprite_lum(wx, wy):
        return lum_steps(wx, wy) * 0.8

    # items on the floor
    for (r, c), name in items:
        if (r, c) in seen:
            blit_sprite(f, SP.ITEM_SPRITES[name], c * CELL + 7, r * CELL + 9, cam,
                        sprite_lum, shadow=False)
    # actors sorted by row so lower ones overlap
    for (r, c), name, opts in sorted(actors, key=lambda a: a[0]):
        if (r, c) not in seen and name != "HERO":
            continue
        art = SP.HERO if name == "HERO" else SP.CREATURE_SPRITES[name]
        ox, oy = opts.get("offset", (0, 0))
        blit_sprite(f, art, c * CELL + 4 + ox, r * CELL + 2 + oy, cam,
                    (lambda wx, wy: 0) if name == "HERO" else sprite_lum,
                    flash=opts.get("flash"))
    if effects:
        effects(f, cam)
    return f


# ---- HUD -----------------------------------------------------------------
HEART = """
.kk...kk.
krrk.krrk
krwrkrrrk
krrrrrrrk
krrrrrrrk
.krrrrrk.
..krrrk..
...krk...
....k....
"""


def draw_text(rom, f, x, y, s, col):
    for i, code in enumerate(text_codes(s)):
        rows = glyph(rom, code)
        for r in range(7):
            for b in range(5):
                if (rows[r] >> (4 - b)) & 1:
                    f.put(x + i * 6 + b, y + r, col)


def draw_hud(rom, f, left, right, lines, heart_big=True):
    for y in range(PF_H, H):
        for x in range(W):
            f.px[y][x] = K["n"]                   # plum via HUD palette
    for x in range(W):
        f.px[PF_H][x] = K["g"]
        f.px[PF_H + 1][x] = K["k"]
    # hand slots
    for (slot_x, (icon, name)) in ((4, left), (W - 4 - 120, right)):
        for y in range(PF_H + 4, PF_H + 18):
            for x in range(slot_x, slot_x + 14):
                edge = y in (PF_H + 4, PF_H + 17) or x in (slot_x, slot_x + 13)
                f.px[y][x] = K["t"] if edge else K["k"]
        if icon:
            rows = SP.parse(SP.ITEM_SPRITES[icon])
            for j, row in enumerate(rows):
                for i, ch in enumerate(row):
                    if ch != ".":
                        f.put(slot_x + 2 + i, PF_H + 6 + j, K[ch])
        draw_text(rom, f, slot_x + 18, PF_H + 8, name, K["g"])
    rows = SP.parse(HEART)
    hx = W // 2 - (len(rows[0]) * (2 if heart_big else 1)) // 2
    s = 2 if heart_big else 1
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                for a in range(s):
                    for b in range(s):
                        f.put(hx + i * s + a, PF_H + 3 + j * s + b, K[ch])
    for i, line in enumerate(lines[-1:]):
        draw_text(rom, f, 4, PF_H + 22, line, K["c"])
    # cursor
    for x in range(4 + len(lines[-1]) * 6, 4 + len(lines[-1]) * 6 + 5):
        f.put(x, PF_H + 29, K["w"])


# ---- scenes ------------------------------------------------------------------
def bfs(lv, start, limit):
    from collections import deque
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if dist[cur] >= limit:
            continue
        for d, (dr, dc) in enumerate(DIRS):
            nb = (cur[0] + dr, cur[1] + dc)
            if nb in dist or lv.is_rock(*nb):
                continue
            if lv.side(cur[0], cur[1], d) in (PAS, DOR):
                dist[nb] = dist[cur] + 1
                q.append(nb)
    return dist


def explored_from(lv, path_cells, radius=6):
    """Squares the hero saw while walking this path."""
    ex = set()
    for p in path_cells:
        if not lv.is_rock(*p):
            ex |= visible_cells(lv, p, radius)
    return ex


def slash(hero, target):
    """Sword arc from the hero toward a target cell."""
    def fx(f, cam):
        hx, hy = hero[1] * CELL + CELL // 2 - cam[0], hero[0] * CELL + CELL // 2 - 4 - cam[1]
        tx, ty = target[1] * CELL + CELL // 2 - cam[0], target[0] * CELL + CELL // 2 - 4 - cam[1]
        ang = math.atan2(ty - hy, tx - hx)
        for k in range(26):
            a = ang - 0.9 + 1.8 * k / 25
            for rr, col in ((13, "w"), (12, "y"), (11, "s")):
                f.put(int(hx + rr * math.cos(a)), int(hy + rr * math.sin(a)), K[col])
        # impact sparks
        for i in range(10):
            a = hash01(i, 1) * 6.28
            d = 2 + hash01(i, 2) * 6
            f.put(int(tx + d * math.cos(a)), int(ty + 4 + d * math.sin(a)),
                  K["r"] if i % 3 else K["y"])
    return fx


def sparkles(center, n=26, cols=("v", "c", "w")):
    def fx(f, cam):
        cx, cy = center[1] * CELL + CELL // 2 - cam[0], center[0] * CELL + CELL // 2 - 4 - cam[1]
        for i in range(n):
            a = hash01(i, 7) * 6.28
            d = 9 + hash01(i, 8) * 14
            f.put(int(cx + d * math.cos(a)), int(cy + d * 0.8 * math.sin(a)),
                  K[cols[i % len(cols)]])
    return fx


def full_map(rom, lv, hero):
    """The SEER scroll: whole level, 5px per cell, creatures as dots."""
    f = Frame()
    S = 5
    ox, oy = (W - 32 * S) // 2, (PF_H - 32 * S) // 2 + 2
    for y in range(PF_H):
        for x in range(W):
            # parchment-dark frame
            f.px[y][x] = K["k"] if BAYER[y & 3][x & 3] < 13 else K["n"]
    for r in range(32):
        for c in range(32):
            x0, y0 = ox + c * S, oy + r * S
            rock = lv.is_rock(r, c)
            for y in range(S):
                for x in range(S):
                    f.put(x0 + x, y0 + y, K["k"] if rock else K["d"])
            if rock:
                continue
            for d, (dr, dc) in enumerate(DIRS):
                s = lv.side(r, c, d)
                if s in (DOR, SDR) and not lv.is_rock(r + dr, c + dc):
                    col = K["b"] if s == DOR else K["v"]
                    for i in range(1, S - 1):
                        if d == 0:
                            f.put(x0 + i, y0, col)
                        elif d == 2:
                            f.put(x0 + i, y0 + S - 1, col)
                        elif d == 1:
                            f.put(x0 + S - 1, y0 + i, col)
                        else:
                            f.put(x0, y0 + i, col)
            if (r, c) in lv.vert:
                f.put(x0 + 2, y0 + 2, K["c"])
                f.put(x0 + 1, y0 + 2, K["c"])
                f.put(x0 + 3, y0 + 2, K["c"])
                f.put(x0 + 2, y0 + 1, K["c"])
                f.put(x0 + 2, y0 + 3, K["c"])
            if (r, c) in lv.creatures:
                for y in range(1, 4):
                    for x in range(1, 4):
                        f.put(x0 + x, y0 + y, K["r"])
    hr, hc = hero
    for y in range(0, 5):
        for x in range(0, 5):
            if (x in (0, 4)) != (y in (0, 4)) or (x, y) == (2, 2):
                f.put(ox + hc * S + x, oy + hr * S + y, K["w"])
    # frame
    for x in range(ox - 3, ox + 32 * S + 3):
        f.put(x, oy - 3, K["g"])
        f.put(x, oy + 32 * S + 2, K["g"])
    for y in range(oy - 3, oy + 32 * S + 3):
        f.put(ox - 3, y, K["g"])
        f.put(ox + 32 * S + 2, y, K["g"])
    return f


def sprite_sheet(rom):
    f = Frame()
    for y in range(H):
        for x in range(W):
            f.px[y][x] = K["k"]
    names = list(SP.CREATURE_SPRITES)
    for i, n in enumerate(["HERO"] + names):
        art = SP.HERO if n == "HERO" else SP.CREATURE_SPRITES[n]
        col, row = i % 7, i // 7
        x0, y0 = 10 + col * 44, 10 + row * 60
        rows = SP.parse(art)
        for j, r in enumerate(rows):
            for k, ch in enumerate(r):
                if ch != ".":
                    for a in range(2):
                        for b in range(2):
                            f.put(x0 + k * 2 + a, y0 + j * 2 + b, K[ch])
    for i, n in enumerate(SP.ITEM_SPRITES):
        rows = SP.parse(SP.ITEM_SPRITES[n])
        x0, y0 = 16 + i * 50, 140
        for j, r in enumerate(rows):
            for k, ch in enumerate(r):
                if ch != ".":
                    for a in range(2):
                        for b in range(2):
                            f.put(x0 + k * 2 + a, y0 + j * 2 + b, K[ch])
    return f


def straight(lv, a, d, n):
    """Cells walking n steps from a in direction d through open passages."""
    cells = [a]
    for _ in range(n):
        cur = cells[-1]
        nb = (cur[0] + DIRS[d][0], cur[1] + DIRS[d][1])
        if not step_open(lv, cur, nb):
            return None
        cells.append(nb)
    return cells


def adjacent_spot(lv, kind):
    for pos, n in sorted(lv.creatures.items()):
        if n != kind:
            continue
        for d in (3, 1, 2, 0):       # prefer side-on views
            run = straight(lv, pos, d, 3)
            if run and not any(c in lv.creatures for c in run[1:]):
                return pos, run[1]
    raise SystemExit("no spot for " + kind)


def spot_with_view(lv, target, n):
    for d in (2, 1, 3, 0):
        run = straight(lv, target, d, n + 2)
        if run:
            return run[n]
    for d in range(4):
        run = straight(lv, target, d, n)
        if run:
            return run[n]
    raise SystemExit("no view of %r" % (target,))


def run_from(lv, a, toward, n):
    """Pretend the hero walked here: a few squares behind them."""
    d = (a[0] - toward[0], a[1] - toward[1])
    step = ((d[0] > 0) - (d[0] < 0), (d[1] > 0) - (d[1] < 0))
    cells = [a]
    for _ in range(n):
        nb = (cells[-1][0] + step[0], cells[-1][1] + step[1])
        if lv.is_rock(*nb):
            break
        cells.append(nb)
    return cells + [toward]


def secret_corridor(lv):
    """An east-west run of 5 open squares with a secret door along it."""
    for r in range(32):
        for c in range(32):
            run = straight(lv, (r, c), 1, 5)
            if not run:
                continue
            if any(lv.side(rr, cc, d) == SDR and not lv.is_rock(rr + DIRS[d][0], cc + DIRS[d][1])
                   for rr, cc in run for d in (0, 2)):
                return run[0], run[4]
    raise SystemExit("no secret corridor")


def scenes(rom, lv):
    out = []
    hero = lv.player
    # 1. the real start position, pine torch lit, walking north
    path = [hero] + [(hero[0] + i, hero[1]) for i in range(1, 4)]
    ex = explored_from(lv, path, 3)
    world = build_world(lv)
    f = render_view(lv, world, hero, 0, 7, ex,
                    [(hero, "HERO", {})] + [(p, n, {}) for p, n in lv.creatures.items()])
    draw_hud(rom, f, (None, "EMPTY"), ("FTORCH", "PINE TORCH"), [".USE RIGHT"])
    out.append(("start", "Level 1 start, pine torch", "Real position and maze from the game's RAM. A pine torch lights about three squares; beyond that is only what you remember.", f))

    # 2. combat: a real spider, hero standing in the next square with a view
    sp, hero2 = adjacent_spot(lv, "SPIDER")
    ex2 = explored_from(lv, run_from(lv, hero2, sp, 4), 3)
    f = render_view(lv, world, hero2, 0, 10, ex2,
                    [(hero2, "HERO", {}), (sp, "SPIDER", {"flash": "w"})] +
                    [(p, n, {}) for p, n in lv.creatures.items() if p != sp],
                    effects=slash(hero2, sp))
    draw_hud(rom, f, ("FSWORD", "WOODEN SWORD"), ("FTORCH", "LUNAR TORCH"), [".ATTACK RIGHT"])
    out.append(("combat", "Striking a spider, lunar torch",
                f"This spider really is at row {sp[0]}, column {sp[1]} of level 1. The sword arc, white hit flash and sparks are sprite effects.", f))

    # 3. the club giant at the pit, seen from two squares away, dropped loot
    g = (15, 4)
    hero3 = spot_with_view(lv, g, 2)
    mid = ((g[0] + hero3[0]) // 2, (g[1] + hero3[1]) // 2)
    ex3 = explored_from(lv, run_from(lv, hero3, g, 4), 3)
    items = [(mid, "FSHIEL")]
    f = render_view(lv, world, hero3, 0, 10, ex3,
                    [(hero3, "HERO", {})] +
                    [(p, n, {}) for p, n in lv.creatures.items()],
                    items=items)
    draw_hud(rom, f, (None, "EMPTY"), ("FTORCH", "LUNAR TORCH"), [".GET LEFT LEATHER SHIELD"])
    out.append(("giant", "Club giant at the pit",
                "The club giant and the hole down really share row 15, column 4 of level 1. The shield on the floor is staged.", f))

    # 4. magic: the Wizard in a corridor with a secret door (staged)
    world_m = build_world(lv, reveal_secret=True)
    hero4, wiz = secret_corridor(lv)
    ex4 = explored_from(lv, run_from(lv, hero4, wiz, 4), 3)
    f = render_view(lv, world_m, hero4, 1, 11, ex4,
                    [(hero4, "HERO", {}), (wiz, "WIZ1", {})],
                    effects=sparkles(wiz), glow=(wiz[1] * CELL + CELL // 2, wiz[0] * CELL + CELL // 2, 9))
    draw_hud(rom, f, ("FRING", "JOULE RING"), ("FTORCH", "SOLAR TORCH"), [".INCANT ..."])
    out.append(("wizard", "The Wizard (staged)", "The Wizard lives on the deepest level; here he stands in a real level-1 corridor to show magic light: his own glow, sparkles, and secret doors revealed in violet.", f))

    # 5. SEER scroll map
    f = full_map(rom, lv, hero)
    draw_hud(rom, f, ("FSCROL", "SEER SCROLL"), ("FTORCH", "PINE TORCH"), [".USE LEFT"])
    out.append(("map", "Seer scroll: the whole level", "Every square of the real level-1 maze. Red marks are the 24 creatures where they actually were, cyan marks are the ladders and holes, brown and violet ticks are doors and secret doors.", f))

    # 6. sprite sheet
    f = sprite_sheet(rom)
    out.append(("sprites", "Sprite sheet", "Hero, all twelve creatures and the six item types, shown at 2x. Each is 16x16 or smaller, 16 colours.", f))
    return out


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(HERE)), "build", "topdown")
    os.makedirs(out, exist_ok=True)
    rom = Rom()
    lv = Level(rom, os.path.join(os.path.dirname(HERE), "level1_ram.hex"))
    for name, title, note, f in scenes(rom, lv):
        img = f.image()
        img.save(os.path.join(out, f"{name}.png"))
        img.resize((W * 3, int(H * 3.6)), Image.NEAREST).save(os.path.join(out, f"{name}_x3.png"))
        print(name)


if __name__ == "__main__":
    main()
