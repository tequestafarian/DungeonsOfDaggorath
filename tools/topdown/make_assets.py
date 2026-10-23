"""Build the CoCo 3 top-down assets: tiles, sprites and line-of-sight tables.

Writes into the build directory:
  td_blk00-04.bin tile sets lit at levels 3,2,1,0 and the "remembered"
                  set (8K each, physical MMU blocks $00-$04)
  td_blk05-06.bin sprites full and dim, each followed by the
                  line-of-sight table (physical blocks $05-$06)
  TDTAB.ASM       equates for the layouts above (included by ENGINE.ASM)
  td_preview.png  a frame composed exactly the way the engine composes it,
                  from the level 1 RAM dump in tools/level1_ram.hex

Pixels are 4bpp, two per byte, left pixel in the high nibble.

usage: python -I tools/topdown/make_assets.py <builddir>
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import sprites as SP  # noqa: E402

CELL = 24
KEYS = "kndstmbgyrelvcow"
K = {ch: i for i, ch in enumerate(KEYS)}


def rgb2(r, g, b):
    return (r * 85, g * 85, b * 85)


PAL = [rgb2(0, 0, 0), rgb2(0, 0, 1), rgb2(1, 1, 1), rgb2(2, 2, 2),
       rgb2(1, 1, 2), rgb2(1, 0, 0), rgb2(2, 1, 0), rgb2(3, 2, 0),
       rgb2(3, 3, 2), rgb2(3, 0, 0), rgb2(0, 2, 0), rgb2(1, 3, 1),
       rgb2(2, 0, 3), rgb2(0, 3, 3), rgb2(3, 1, 0), rgb2(3, 3, 3)]


def gime(rgb):
    """CoCo 3 RGB palette byte: R1 G1 B1 R0 G0 B0."""
    r, g, b = (v // 85 for v in rgb)
    return ((r >> 1) << 5) | ((g >> 1) << 4) | ((b >> 1) << 3) | \
        ((r & 1) << 2) | ((g & 1) << 1) | (b & 1)


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


def dith(x, y, tone):
    return BAYER[y & 3][x & 3] < tone * 16


class Img:
    """A small palette-index bitmap; None = transparent."""

    def __init__(self, w, h, fill=0):
        self.w, self.h = w, h
        self.p = [[fill] * w for _ in range(h)]

    def put(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.p[y][x] = K[c] if isinstance(c, str) else c

    def map(self, fn):
        out = Img(self.w, self.h)
        out.p = [[fn(x, y, c) for x, c in enumerate(row)] for y, row in enumerate(self.p)]
        return out


# ---- tile art (24x24, everything drawn inside its own cell) ----------------
FACE = 11      # brick face on the south side of rock
RIM = 4


def floor_tile(v):
    t = Img(CELL, CELL)
    S = 12
    for y in range(CELL):
        for x in range(CELL):
            row = y // S
            off = (S // 2) if row % 2 else 0
            gx, gy = (x + off) % S, y % S
            h = hash01((x + off) // S, row, v, 3)
            if gx == 0 or gy == 0:
                c = "k"
            elif gx == 1 or gy == 1:
                c = "s" if h > 0.25 else "d"
            elif gx == S - 1 or gy == S - 1:
                c = "n"
            else:
                c = "s" if dith(x, y, 0.15 + 0.45 * h) else "d"
            t.put(x, y, c)
    if v in (1, 3):                                   # a crack
        x, y = 4 + int(hash01(v, 1) * 14), 3 + int(hash01(v, 2) * 6)
        for i in range(7):
            t.put(x, y, "k")
            x += 1 if hash01(v, i) < 0.6 else 0
            y += 1
    return t


def floor_memory(t):
    """Remembered floor: black, with a navy dot where the joints cross."""
    out = Img(CELL, CELL)
    for y in (0, 12):
        for x in range(0, CELL, 6):
            out.put(x if y == 0 else (x + 3) % CELL, y, "n")
    return out


def rock_tile(mask):
    """Solid rock. mask bit d set = neighbour in direction d is open floor."""
    open_ = [bool(mask >> d & 1) for d in range(4)]
    t = Img(CELL, CELL)
    m = Img(CELL, CELL)
    face_top = CELL - FACE if open_[2] else CELL
    for y in range(face_top):
        for x in range(CELL):
            dist = min([y if open_[0] else 99,
                        (CELL - 1 - x) if open_[1] else 99,
                        (face_top - 1 - y) if open_[2] else 99,
                        x if open_[3] else 99])
            if dist == 0:
                t.put(x, y, "s" if (open_[2] and y == face_top - 1) else "t")
                m.put(x, y, "n")
            elif dist < RIM:
                tone = 0.8 - dist * 0.22 + (hash01(x // 2, y // 2, mask) - 0.5) * 0.3
                t.put(x, y, "t" if dith(x, y, tone) else "n")
    if open_[2]:
        for y in range(FACE):
            for x in range(CELL):
                course = y // 4
                bx = (x + (6 if course % 2 else 0)) % 12
                if y % 4 == 3 or bx == 0:
                    c = "k"
                else:
                    h = hash01((x + 6 * course) // 12, y // 4, 11)
                    tone = 0.75 + 0.25 * h - y * 0.055 + (0.25 if y % 4 == 0 else 0)
                    c = "s" if dith(x, y, tone - 0.5) else ("d" if dith(x, y, tone) else "n")
                t.put(x, face_top + y, c)
        for x in range(CELL):
            m.put(x, CELL - 1, "n")
    return t, m


def vert_tile(code, base):
    """Floor with a vertical feature. VFIND codes: 0 hole up, 1 ladder up,
    2 hole down, 3 ladder down."""
    t = Img(CELL, CELL)
    t.p = [row[:] for row in base.p]
    m = floor_memory(base)
    cx = cy = CELL / 2
    if code >= 2:
        for y in range(2, CELL - 1):
            for x in range(2, CELL - 2):
                e = ((x + 0.5 - cx) / 9.5) ** 2 + ((y + 0.5 - cy) / 8) ** 2
                if e <= 1:
                    c = "k"
                    if e > 0.78:
                        c = "s" if y > cy else "d"
                    elif e > 0.55 and y < cy:
                        c = "n"
                    t.put(x, y, c)
                    m.put(x, y, "n" if e > 0.78 else "k")
        if code == 3:
            for y in range(5, CELL - 4):
                t.put(8, y, "b")
                t.put(15, y, "b")
                if y % 4 == 1:
                    for x in range(9, 15):
                        t.put(x, y, "g" if y < cy else "m")
    else:
        for y in range(CELL):
            for x in range(CELL):
                if abs(x - cx) + abs(y - cy) < 10 and dith(x, y, 0.3):
                    t.put(x, y, "t")
                    if dith(x, y, 0.08):
                        m.put(x, y, "n")
        if code == 1:
            for y in range(1, CELL - 1):
                t.put(7, y, "g")
                t.put(16, y, "g")
                m.put(7, y, "n")
                m.put(16, y, "n")
                if y % 4 == 0:
                    for x in range(8, 16):
                        t.put(x, y, "b")
    return t, m


# Edge strips.  A wall or door on the boundary between two open cells is
# drawn half in each: the top of the wall in the north/west cell, its face
# (or the door) in the south/east cell.
NS_H, SS_H, EW_W = 5, 3, 4     # rows of N strip, rows of S strip, px of E/W


def strip_n(kind):
    """Rows 0-4 of the cell south of the boundary: the wall's face."""
    t, m = Img(CELL, NS_H), Img(CELL, NS_H)
    for y in range(NS_H):
        for x in range(CELL):
            if kind == "wall":
                c = "k" if (y == NS_H - 1 or x % 12 == 0) else ("d" if y < 2 else "n")
            else:
                wood, dark, band = ("b", "m", "d") if kind == "door" else ("v", "n", "c")
                if x < 3 or x >= CELL - 3:
                    c = "d" if x in (1, CELL - 2) else "k"
                elif y == NS_H - 1:
                    c = "k"
                else:
                    c = dark if x % 4 == 3 else wood
                    if y == 1:
                        c = band
            t.put(x, y, c)
            if y == 0:
                m.put(x, y, "n")
    if kind != "wall":
        t.put(CELL // 2 + 3, 2, "g" if kind == "door" else "w")
    if kind == "secret":
        for i in range(5):
            t.put(3 + int(hash01(i, 7) * 18), int(hash01(7, i) * 4), "w" if i % 2 else "c")
    return t, m


def strip_s(kind):
    """Rows 21-23 of the cell north of the boundary: the top of the wall."""
    t, m = Img(CELL, SS_H), Img(CELL, SS_H)
    for y in range(SS_H):
        for x in range(CELL):
            if kind == "wall":
                c = "s" if y == 0 else "t"
            else:
                c = "s" if y == 0 else ("t" if (x < 3 or x >= CELL - 3) else
                                        ("g" if kind == "door" else "c"))
            t.put(x, y, c)
            if y == SS_H - 1:
                m.put(x, y, "n")
    return t, m


def strip_ew(kind, east):
    """Columns 20-23 (east) or 0-3 (west): a wall seen from above."""
    t, m = Img(EW_W, CELL), Img(EW_W, CELL)
    for y in range(CELL):
        for x in range(EW_W):
            edge = x == (EW_W - 1 if east else 0)      # on the boundary
            inner = x == (0 if east else EW_W - 1)
            if kind == "wall":
                c = "k" if inner else ("t" if edge else "s")
            else:
                wood, dark = ("b", "m") if kind == "door" else ("v", "n")
                if y < 3 or y > CELL - 4:
                    c = "k" if inner else "t"
                elif inner:
                    c = "k"
                else:
                    c = dark if y % 4 == 3 else wood
            t.put(x, y, c)
            if edge:
                m.put(x, y, "n")
    if kind != "wall":
        t.put(EW_W - 1 if east else 0, CELL // 2, "g" if kind == "door" else "w")
    return t, m


STRIP_KINDS = ["wall", "door", "secret"]


def light_variant(img, level):
    """Level 3 = as drawn; each lower level is half a step darker, dithered
    between neighbouring shades."""
    if level == 3:
        return img
    if level == 2:
        return img.map(lambda x, y, c: c if dith(x, y, 0.5) else DARKER[c])
    if level == 1:
        return img.map(lambda x, y, c: DARKER[c])
    return img.map(lambda x, y, c: DARKER[c] if dith(x, y, 0.5) else DARKER[DARKER[c]])


# ---- packing ---------------------------------------------------------------
def pack(img):
    """Opaque rows, 2 pixels per byte."""
    out = bytearray()
    for row in img.p:
        for x in range(0, img.w, 2):
            out.append((row[x] << 4) | row[x + 1])
    return bytes(out)


def pack_masked(rows, wbytes):
    """Per row, per byte: mask then data.  Transparent nibbles: mask F."""
    out = bytearray()
    for row in rows:
        row = row + [None] * (wbytes * 2 - len(row))
        for x in range(0, wbytes * 2, 2):
            a, b = row[x], row[x + 1]
            mask = (0xF0 if a is None else 0) | (0x0F if b is None else 0)
            data = ((a or 0) << 4) | (b or 0)
            out += bytes((mask, data))
    return bytes(out)


def art_rows(art, pad_left=0):
    rows = SP.parse(art)
    return [[None] * pad_left + [None if ch == "." else K[ch] for ch in r] for r in rows]


def dim_rows(rows):
    return [[None if c is None else DARKER[c] for c in r] for r in rows]


ARROWS = {   # facing marker, gold chevrons: N, E, S, W
    0: ["...gg...", "..gyyg..", ".gk..kg.", "gk....kg"],
    2: ["gk....kg", ".gk..kg.", "..gyyg..", "...gg..."],
    1: ["g...", "kg..", ".kg.", "..yg", "..yg", ".kg.", "kg..", "g..."],
    3: ["...g", "..gk", ".gk.", "gy..", "gy..", ".gk.", "..gk", "...g"],
}


def arrow_rows(d):
    return [[None if ch == "." else K[ch] for ch in r] for r in ARROWS[d]]


CRE_ORDER = ["SPIDER", "VIPER", "SGINT1", "BLOB", "KNIGT1", "SGINT2",
             "SCORP", "KNIGT2", "WRAITH", "BALROG", "WIZ0", "WIZ1"]
ITEM_ORDER = ["FFLASK", "FRING", "FSCROL", "FSHIEL", "FSWORD", "FTORCH"]

# Block layouts (addresses as seen through MMU slot 5, $A000-$BFFF)
BANK = 0xA000
TILE_SZ = CELL * CELL // 2                      # 288
T_FLOOR = BANK                                  # 4 variants
T_VERT = T_FLOOR + 4 * TILE_SZ                  # 4 VFIND codes
T_ROCK = T_VERT + 4 * TILE_SZ                   # 16 open-neighbour masks
T_STRN = T_ROCK + 16 * TILE_SZ                  # 3 kinds, 5 rows x 12
T_STRS = T_STRN + 3 * NS_H * 12                 # 3 kinds, 3 rows x 12
T_STRE = T_STRS + 3 * SS_H * 12                 # 3 kinds, 24 rows x 2
T_STRW = T_STRE + 3 * CELL * 2
T_END = T_STRW + 3 * CELL * 2

S_CRE = BANK                                    # 12 x 16 rows x 16 bytes
S_HERO = S_CRE + 12 * 256
S_ARRN = S_HERO + 256                           # 4 rows x 8 bytes
S_ARRS = S_ARRN + 32
S_ARRE = S_ARRS + 32                            # 8 rows x 4 bytes
S_ARRW = S_ARRE + 32
S_ITEM = S_ARRW + 32                            # 6 x 10 rows x 12 bytes
S_END = S_ITEM + 6 * 120
LOS_TAB = 0xB400                                # 91 x 20 bytes
LOS_REC = 20

TILE_BLK0, SPR_BLK = 0x00, 0x05                 # physical MMU blocks
VIEW_R, VIEW_C = 3, 6                           # window half sizes (7 x 13)


def build_tiles():
    """Returns list of 5 blocks and a dict of level-3 / memory Imgs used by
    the preview."""
    floors = [floor_tile(v) for v in range(4)]
    verts = [vert_tile(c, floors[0]) for c in range(4)]
    rocks = [rock_tile(m) for m in range(16)]
    strips = {
        "n": [strip_n(k) for k in STRIP_KINDS],
        "s": [strip_s(k) for k in STRIP_KINDS],
        "e": [strip_ew(k, True) for k in STRIP_KINDS],
        "w": [strip_ew(k, False) for k in STRIP_KINDS],
    }
    sets = {}
    blocks = []
    for lvl in (3, 2, 1, 0, "m"):
        if lvl == "m":
            parts = ([floor_memory(f) for f in floors] + [m for _, m in verts] +
                     [m for _, m in rocks] +
                     [m for _, m in strips["n"]] + [m for _, m in strips["s"]] +
                     [m for _, m in strips["e"]] + [m for _, m in strips["w"]])
        else:
            parts = [light_variant(i, lvl) for i in
                     (floors + [t for t, _ in verts] + [t for t, _ in rocks] +
                      [t for t, _ in strips["n"]] + [t for t, _ in strips["s"]] +
                      [t for t, _ in strips["e"]] + [t for t, _ in strips["w"]])]
        sets[lvl] = parts
        data = b"".join(pack(p) for p in parts)
        assert len(data) == T_END - BANK, (len(data), T_END - BANK)
        blocks.append(data.ljust(8192, b"\0"))
    return blocks, sets


def los_paths(dr, dc):
    """Supercover line from the centre of (0,0) to the centre of (dr,dc).
    Returns two step lists (directions 0-3) which differ only where the line
    passes exactly through a corner: A crosses rows first, B columns first."""
    paths = []
    for rows_first in (True, False):
        steps = []
        r = c = 0
        sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
        while (r, c) != (dr, dc):
            # parameter t at which the line crosses the next row / col boundary
            tr = (abs(r) + 0.5) / abs(dr) if dr else 9
            tc = (abs(c) + 0.5) / abs(dc) if dc else 9
            if abs(tr - tc) < 1e-9:
                order = ["r", "c"] if rows_first else ["c", "r"]
            else:
                order = ["r"] if tr < tc else ["c"]
            for o in order:
                if o == "r":
                    r += sr
                    steps.append(2 if sr > 0 else 0)
                else:
                    c += sc
                    steps.append(1 if sc > 0 else 3)
        paths.append(steps)
    return paths


def build_los():
    tab = bytearray()
    recs = {}
    for dr in range(-VIEW_R, VIEW_R + 1):
        for dc in range(-VIEW_C, VIEW_C + 1):
            a, b = los_paths(dr, dc)
            dist = int(math.floor(math.hypot(dr, dc) + 0.5))
            assert len(a) == len(b) <= 9
            rec = bytes([dist, len(a)]) + bytes(a).ljust(9, b"\xff") + bytes(b).ljust(9, b"\xff")
            assert len(rec) == LOS_REC
            tab += rec
            recs[(dr, dc)] = (dist, a, b)
    return bytes(tab), recs


def build_sprites():
    blocks = []
    for dim in (False, True):
        f = dim_rows if dim else (lambda r: r)
        data = bytearray()
        for name in CRE_ORDER:
            data += pack_masked(f(art_rows(SP.CREATURE_SPRITES[name])), 8)
        data += pack_masked(f(art_rows(SP.HERO)), 8)
        data += pack_masked(arrow_rows(0), 4)
        data += pack_masked(arrow_rows(2), 4)
        data += pack_masked(arrow_rows(1), 2)
        data += pack_masked(arrow_rows(3), 2)
        for name in ITEM_ORDER:
            data += pack_masked(f(art_rows(SP.ITEM_SPRITES[name], pad_left=1)), 6)
        assert len(data) == S_END - BANK, (len(data), S_END - BANK)
        blocks.append(data)
    return blocks


def write_asm(path, palette):
    eq = [
        ("TDTILE", TILE_BLK0, "first tile set block (lit 3,2,1,0, remembered)"),
        ("TDSPRB", SPR_BLK, "sprite block (full; +1 dim)"),
        ("TDBANK", BANK, "MMU slot 5 window"),
        ("T.FLOR", T_FLOOR, "4 floor tiles, 288 bytes each"),
        ("T.VERT", T_VERT, "4 vertical feature tiles (VFIND code)"),
        ("T.ROCK", T_ROCK, "16 rock tiles (open neighbour mask)"),
        ("T.STRN", T_STRN, "north strips: wall, door, secret (5 rows)"),
        ("T.STRS", T_STRS, "south strips (3 rows)"),
        ("T.STRE", T_STRE, "east strips (24 rows x 2 bytes)"),
        ("T.STRW", T_STRW, "west strips"),
        ("TILESZ", TILE_SZ, "bytes per tile"),
        ("NS.H", NS_H, "north strip rows"),
        ("SS.H", SS_H, "south strip rows"),
        ("S.CRE", S_CRE, "12 creature sprites, 256 bytes each"),
        ("S.HERO", S_HERO, "hero sprite"),
        ("S.ARRN", S_ARRN, "facing arrows N,S (4x4 rows), E,W (2x8 rows)"),
        ("S.ARRS", S_ARRS, ""),
        ("S.ARRE", S_ARRE, ""),
        ("S.ARRW", S_ARRW, ""),
        ("S.ITEM", S_ITEM, "6 item sprites, 120 bytes each"),
        ("LOSTAB", LOS_TAB, "91 x LOSREC: dist, len, path A[9], path B[9]"),
        ("LOSREC", LOS_REC, ""),
    ]
    with open(path, "w", newline="\r\n") as fp:
        fp.write(";  Generated by tools/topdown/make_assets.py - do not edit\n;\n")
        for name, val, note in eq:
            fp.write(f"{name:<8}EQU     ${val:04X}" + (f"           ;{note}" if note else "") + "\n")
        fp.write(";\n;  Top-down palette (RGB: R1 G1 B1 R0 G0 B0)\n;\n")
        fp.write("TDPAL   FCB     " + ",".join(f"${b:02X}" for b in palette) + "\n")


# ---- reference compositor (mirrors ENGINE.ASM TDVIEW) -----------------------
def preview(sets, spr_rows, recs, level, light, mlight, outpath, seen=None):
    from PIL import Image
    W, H = 320, 192
    scr = [[0] * W for _ in range(H)]
    pr, pc = level.player
    maze = level.maze

    def cell(r, c):
        return maze[r * 32 + c] if 0 <= r < 32 and 0 <= c < 32 else None

    def blit(img, x0, y0, wr):
        top = 8 if wr == 0 else 0
        bot = 16 if wr == 2 * VIEW_R else 24
        for y in range(img.h):
            cy = y0 + y
            if not top <= cy < bot:
                continue
            sy = wr * 24 - 8 + cy
            for x in range(img.w):
                v = img.p[y][x]
                if v is not None:
                    scr[sy][x0 + x] = v

    def blit_rows(rows, x0, y0, wr, bx):
        im = Img(len(rows[0]), len(rows))
        im.p = rows
        blit(im, x0 + bx, y0, wr)

    seen = seen if seen is not None else set()
    vis = {}
    for (dr, dc), (dist, a, b) in recs.items():
        r, c = pr + dr, pc + dc
        ok = False
        for path in (a, b):
            rr, cc, good = pr, pc, True
            for d in path:
                v = cell(rr, cc)
                if v is None or v == 0xFF or (v >> (2 * d)) & 3:
                    good = False
                    break
                rr, cc = rr + DIRS[d][0], cc + DIRS[d][1]
            if good and cell(rr, cc) not in (None, 0xFF):
                ok = True
        v = light - 7 - dist
        shade = 3 if v >= 0 else 2 if v >= -2 else 1 if v >= -4 else 0 if v >= -6 else -1
        vis[(dr, dc)] = (ok, shade if ok else -1, dist)
        if ok and shade >= 0:
            seen.add((r, c))

    FL, VT, RK = 0, 4, 8
    SN, SS, SE, SW = 24, 27, 30, 33
    for wr in range(2 * VIEW_R + 1):
        for wc in range(2 * VIEW_C + 1):
            dr, dc = wr - VIEW_R, wc - VIEW_C
            r, c = pr + dr, pc + dc
            x0 = 4 + wc * 24
            v = cell(r, c)
            if v is None:
                continue
            if v == 0xFF:
                best, mem = -1, False
                mask = 0
                for d, (ddr, ddc) in enumerate(DIRS):
                    nv = cell(r + ddr, c + ddc)
                    if nv is not None and nv != 0xFF:
                        mask |= 1 << d
                        n = vis.get((dr + ddr, dc + ddc))
                        if n and n[1] >= 0:
                            best = max(best, n[1])
                        if (r + ddr, c + ddc) in seen:
                            mem = True
                tset = sets[best] if best >= 0 else (sets["m"] if mem else None)
                if tset:
                    blit(tset[RK + mask], x0, 0, wr)
                continue
            ok, shade, dist = vis[(dr, dc)]
            if shade >= 0:
                tset = sets[shade]
            elif (r, c) in seen:
                tset = sets["m"]
            else:
                continue
            vf = level.vert.get((r, c))
            code = {"hole_up": 0, "ladder_up": 1, "hole_dn": 2, "ladder_dn": 3}.get(vf)
            blit(tset[VT + code] if code is not None else tset[FL + ((r * 7 + c * 3) & 3)],
                 x0, 0, wr)
            for d in range(4):
                s = (v >> (2 * d)) & 3
                nv = cell(r + DIRS[d][0], c + DIRS[d][1])
                if s == 0 or nv in (None, 0xFF):
                    continue
                kind = 0 if s == WAL else 1 if s == DOR else (
                    2 if shade >= 0 and mlight - 7 - dist > -7 else 0)
                if d == 0:
                    blit(tset[SN + kind], x0, 0, wr)
                elif d == 2:
                    blit(tset[SS + kind], x0, CELL - SS_H, wr)
                elif d == 1:
                    blit(tset[SE + kind], x0 + CELL - EW_W, 0, wr)
                else:
                    blit(tset[SW + kind], x0, 0, wr)
            if shade < 0:
                continue
            cre = level.creatures.get((r, c))
            if cre:
                rows = spr_rows["cre"][cre]
                if shade < 2:
                    rows = dim_rows(rows)
                blit_rows(rows, x0, 4, wr, 8 if (dr, dc) == (0, 0) else 4)
    hero = spr_rows["hero"]
    x0 = 4 + VIEW_C * 24
    blit_rows(hero, x0, 4, VIEW_R, 0 if level.creatures.get((pr, pc)) else 4)
    pos = {0: (8, 0), 2: (8, 20), 1: (20, 8), 3: (0, 8)}[level.facing]
    blit_rows(arrow_rows(level.facing), x0 + pos[0], pos[1], VIEW_R, 0)
    img = Image.new("RGB", (W, H))
    img.putdata([PAL[v] for row in scr for v in row])
    img.resize((W * 3, H * 3), Image.NEAREST).save(outpath)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "build")
    os.makedirs(out, exist_ok=True)
    tiles, sets = build_tiles()
    sprites = build_sprites()
    los, recs = build_los()
    spr0 = sprites[0]
    assert LOS_TAB - BANK >= len(spr0)
    spr_blocks = [(s.ljust(LOS_TAB - BANK, b"\0") + los).ljust(8192, b"\0") for s in sprites]
    for i, blk in enumerate(tiles + spr_blocks):    # physical blocks $00-$06
        assert len(blk) == 8192
        open(os.path.join(out, f"td_blk{i:02d}.bin"), "wb").write(blk)
    write_asm(os.path.join(out, "TDTAB.ASM"), [gime(c) for c in PAL])
    print(f"tiles {T_END - BANK} bytes/set, sprites {S_END - BANK} bytes, los {len(los)} bytes")

    if "--preview" in sys.argv:
        from dodrom import Rom
        from render_topdown import Level
        rom = Rom()
        lv = Level(rom, os.path.join(HERE, "..", "level1_ram.hex"))
        spr_rows = {"cre": {n: art_rows(SP.CREATURE_SPRITES[n]) for n in CRE_ORDER},
                    "hero": art_rows(SP.HERO)}
        for name, pos, face, light in [("pine", None, 0, 7), ("solar", None, 0, 13)]:
            lv.facing = face
            preview(sets, spr_rows, recs, lv, light, 0,
                    os.path.join(out, f"td_preview_{name}.png"))


if __name__ == "__main__":
    main()
