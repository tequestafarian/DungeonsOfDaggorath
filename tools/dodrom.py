"""Read Dungeons of Daggorath vector data straight out of the assembled ROM.

Mirrors VCTLST.ASM (display list processor), SETFAX (lighting) and
VIEWER.ASM (3-D maze walk) so mockups use the game's real geometry.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V_NEW, V_END, V_JMP, V_REL, V_JSR, V_RTS, V_ABS = 0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0x00
ROM_BASE = 0xC000

# NORSCL from VIEWER.ASM, indexed by RANGE
NORSCL = [200, 128, 80, 50, 31, 20, 12, 8, 4, 2]
CENTER_X, CENTER_Y = 128, 76           # VCNTRX / VCNTRY from COMDAT.ASM
VIEW_H = 152                           # 19 text rows * 8 scan lines

# Creature order from CREXXX (DTABAS.ASM); magic = nonzero magic offense
CREATURES = ["SPIDER", "VIPER", "SGINT1", "BLOB", "KNIGT1", "SGINT2",
             "SCORP", "KNIGT2", "WRAITH", "BALROG", "WIZ0", "WIZ1"]
MAGIC_CREATURES = {"SCORP", "WRAITH", "BALROG", "WIZ0", "WIZ1"}
OBJECTS = ["FFLASK", "FRING", "FSCROL", "FSHIEL", "FSWORD", "FTORCH"]

PAS, DOR, SDR, WAL = 0, 1, 2, 3        # HF.* cell side features


class Rom:
    def __init__(self, rom_path=None, sym_path=None):
        rom_path = rom_path or os.path.join(ROOT, "build", "dod.rom")
        sym_path = sym_path or os.path.join(ROOT, "build", "dod.sym")
        with open(rom_path, "rb") as f:
            self.data = f.read()
        self.sym = {}
        with open(sym_path) as f:
            for line in f:
                m = re.match(r"(\S+) EQU \$([0-9A-F]+)", line)
                if m:
                    self.sym[m.group(1)] = int(m.group(2), 16)

    def byte(self, addr):
        return self.data[addr - ROM_BASE]

    def word(self, addr):
        return (self.byte(addr) << 8) | self.byte(addr + 1)

    def addr(self, name):
        return self.sym[name]

    # ---- VCTLST.ASM -------------------------------------------------
    def segments(self, start, scale, cx=CENTER_X, cy=CENTER_Y):
        """Walk a vector list; return [(x0,y0,x1,y1)] in screen coords.

        Points come back as polylines too: [(points...)] per V$NEW run,
        used by the fill renderer.
        """
        def sc(v, c):
            d = (v - c) & 0xFF
            if v - c < 0:               # SUBB set carry
                r = -(((-(v - c)) & 0xFF) * scale)
            else:
                r = d * scale
            return (r >> 7) + c        # ASRD7 is an arithmetic shift

        segs, runs = [], []
        stack = []
        x = start
        have_start = False
        tx = ty = 0
        p1 = None
        run = []
        while True:
            b = self.byte(x)
            if b >= V_RTS:
                x += 1
                if b == V_END or (b == V_RTS and not stack):
                    break
                if b == V_JSR:
                    stack.append(x + 2)
                    x = self.word(x)
                elif b == V_JMP:
                    x = self.word(x)
                elif b == V_RTS:
                    x = stack.pop()
                if b in (V_JSR, V_JMP, V_RTS, V_NEW):
                    have_start = False
                    if len(run) > 1:
                        runs.append(run)
                    run = []
                    continue
                # V$REL: short relative vectors until V$ABS
                while True:
                    rb = self.byte(x)
                    x += 1
                    if rb == V_ABS:
                        have_start = False
                        if len(run) > 1:
                            runs.append(run)
                        run = []
                        break
                    dy = ((rb >> 4) ^ 8) - 8
                    dx = ((rb & 15) ^ 8) - 8
                    ty = (ty + dy * 2) & 0xFF
                    tx = (tx + dx * 2) & 0xFF
                    p0 = p1
                    p1 = (sc(tx, cx), sc(ty, cy))
                    segs.append((p0[0], p0[1], p1[0], p1[1]))
                    run.append(p1)
                continue
            # absolute point y,x
            ty, tx = self.byte(x), self.byte(x + 1)
            x += 2
            p0 = p1
            p1 = (sc(tx, cx), sc(ty, cy))
            if have_start:
                segs.append((p0[0], p0[1], p1[0], p1[1]))
                run.append(p1)
            else:
                have_start = True
                if len(run) > 1:
                    runs.append(run)
                run = [p1]
        if len(run) > 1:
            runs.append(run)
        return segs, runs

    def table_entry(self, table, index):
        return self.word(self.addr(table) + 2 * index)


# ---- SETFAX (VCTLST.ASM) ---------------------------------------------
BITMSK = [0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01]


def fade(light, rng):
    """Return VCTFAD: 0 = solid, n = plot every (n+1)th dot, -1 = invisible."""
    a = light - 7 - rng
    if a >= 0:
        return 0
    if a <= -7:
        return -1
    return BITMSK[8 + a]


def brightness(light, rng):
    """Same lighting as fade(), as a level: 7 = solid line .. 1 = every
    33rd dot, 0 = invisible."""
    a = light - 7 - rng
    return max(0, min(7, 7 + a))


# ---- VIEWER.ASM --------------------------------------------------------
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]   # N E S W as (drow, dcol)


class Scene:
    """A small hand-built maze in the game's own terms.

    walls[(r,c)] = [N,E,S,W] side features (PAS/DOR/SDR/WAL)
    """

    def __init__(self, walls, prow, pcol, pdir, rlight, mlight=0,
                 creatures=None, objects=None, vert=None, name=""):
        self.walls = walls
        self.prow, self.pcol, self.pdir = prow, pcol, pdir
        self.rlight, self.mlight = rlight, mlight
        self.creatures = creatures or {}   # (r,c) -> name
        self.objects = objects or {}       # (r,c) -> [names]
        self.vert = vert or {}             # (r,c) -> 0..3 (FWDVER index)
        self.name = name

    def side(self, cell, d):
        return self.walls.get(cell, [WAL] * 4)[d % 4]


def walk(rom, scene):
    """Replay VIEWER: return draw calls front-to-back as dicts.

    Each call: kind, name, range, scale, light (fade source), magic,
    segs, runs.  kind in wall/door/sdoor/passage/creature/peek/vert/ceiling/object
    """
    calls = []
    cell = (scene.prow, scene.pcol)
    flat = rom.addr("FLATAB")
    side_kind = {PAS: "passage", DOR: "door", SDR: "sdoor", WAL: "wall"}
    side_name = {3: "L", 0: "F", 1: "R"}

    def add(kind, name, addr, rng, magic, extra=None):
        light = scene.mlight if magic else scene.rlight
        segs, runs = rom.segments(addr, NORSCL[rng])
        c = dict(kind=kind, name=name, range=rng, magic=magic,
                 fade=fade(light, rng), bright=brightness(light, rng),
                 segs=segs, runs=runs, cell=cell)
        if extra:
            c.update(extra)
        calls.append(c)

    for rng in range(10):
        y = flat
        while True:
            rel = rom.byte(y)
            if rel >= 0x80:
                break
            feat = scene.side(cell, scene.pdir + rel)
            sname = side_name[rel]
            if feat == SDR:
                add("sdoor", sname, rom.word(y + 1 + 2 * SDR), rng, True,
                    {"side": sname})
                feat = WAL
            add(side_kind[feat], sname, rom.word(y + 1 + 2 * feat), rng, False,
                {"side": sname})
            y += 9
        # creature in this cell
        if cell in scene.creatures:
            cn = scene.creatures[cell]
            add("creature", cn, rom.table_entry("FWDCRE", CREATURES.index(cn)),
                rng, cn in MAGIC_CREATURES)
        # peek-a-boo left / right
        for rel, lab in ((3, "LPEEK"), (1, "RPEEK")):
            if scene.side(cell, scene.pdir + rel) == PAS:
                d = DIRS[(scene.pdir + rel) % 4]
                nb = (cell[0] + d[0], cell[1] + d[1])
                if nb in scene.creatures:
                    add("peek", scene.creatures[nb], rom.addr(lab), rng,
                        scene.creatures[nb] in MAGIC_CREATURES)
        if cell in scene.vert:
            add("vert", str(scene.vert[cell]),
                rom.table_entry("FWDVER", scene.vert[cell]), rng, False)
        else:
            add("ceiling", "CELINE", rom.addr("CELINE"), rng, False)
        for on in scene.objects.get(cell, []):
            a = rom.table_entry("FWDOBJ", OBJECTS.index(on))
            add("object", on, a, rng, True)
            add("object", on, a, rng, False)
        if scene.side(cell, scene.pdir) != PAS:
            break
        d = DIRS[scene.pdir]
        cell = (cell[0] + d[0], cell[1] + d[1])
    return calls


# ---- SWCHAR.ASM font ---------------------------------------------------
CHARSET = " ABCDEFGHIJKLMNOPQRSTUVWXYZ!_?."


def glyph(rom, code):
    base = rom.addr("SWCTAB") + code * 5
    bits = 0
    for i in range(5):
        bits = (bits << 8) | rom.byte(base + i)
    rows = []
    for r in range(7):
        rows.append((bits >> (30 - 5 * r)) & 31)
    return rows


def text_codes(s):
    out = []
    for ch in s.upper():
        if ch in CHARSET:
            out.append(CHARSET.index(ch))
        elif ch == "<":
            out.append(0x20)   # small heart left
        elif ch == ">":
            out.append(0x21)   # small heart right
        else:
            out.append(0)
    return out
