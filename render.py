"""Tiny deterministic canvas: TrueType outlines, scanline coverage, PNG.

No third-party libraries. Glyphs are read from the bundled Liberation fonts,
flattened to polygons, and filled with a nonzero-winding supersampler.
The same inputs always produce the same PNG bytes.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from array import array


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _s16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


class Font:
    """A TrueType font, parsed far enough to draw Latin news text."""

    def __init__(self, path: str):
        self.data = open(path, "rb").read()
        self.tables: dict[bytes, tuple[int, int]] = {}
        ntables = _u16(self.data, 4)
        for i in range(ntables):
            rec = 12 + i * 16
            tag = self.data[rec : rec + 4]
            off = _u32(self.data, rec + 8)
            length = _u32(self.data, rec + 12)
            self.tables[tag] = (off, length)
        head = self.table(b"head")
        self.upem = _u16(head, 18)
        self.index_to_loc = _s16(head, 50)
        hhea = self.table(b"hhea")
        self.ascent = _s16(hhea, 4)
        self.descent = _s16(hhea, 6)
        self.line_gap = _s16(hhea, 8)
        self.num_h_metrics = _u16(hhea, 34)
        maxp = self.table(b"maxp")
        self.num_glyphs = _u16(maxp, 4)
        self.glyf = self.table(b"glyf")
        self._parse_hmtx()
        self._parse_loca()
        self._parse_cmap()
        self._parse_kern()
        self._outlines: dict[int, list[list[tuple[float, float]]]] = {}

    def table(self, tag: bytes) -> bytes:
        off, length = self.tables[tag]
        return self.data[off : off + length]

    def _parse_hmtx(self) -> None:
        raw = self.table(b"hmtx")
        self.advances: list[int] = []
        self.lsbs: list[int] = []
        n = self.num_h_metrics
        for i in range(n):
            aw, lsb = struct.unpack_from(">Hh", raw, i * 4)
            self.advances.append(aw)
            self.lsbs.append(lsb)
        pos = n * 4
        for _ in range(self.num_glyphs - n):
            self.lsbs.append(_s16(raw, pos))
            pos += 2

    def _parse_loca(self) -> None:
        raw = self.table(b"loca")
        count = self.num_glyphs + 1
        if self.index_to_loc == 0:
            vals = struct.unpack_from(f">{count}H", raw, 0)
            self.loca = [v * 2 for v in vals]
        else:
            self.loca = list(struct.unpack_from(f">{count}I", raw, 0))

    def _parse_cmap(self) -> None:
        data = self.table(b"cmap")
        num = _u16(data, 2)
        chosen = None
        for i in range(num):
            plat, enc, off = struct.unpack_from(">HHI", data, 4 + i * 8)
            fmt = _u16(data, off)
            rank = None
            if fmt == 4 and (plat, enc) in ((3, 1), (0, 3)):
                rank = 0
            elif fmt == 4:
                rank = 1
            elif fmt == 12 and chosen is None:
                rank = 2
            if rank is not None and (chosen is None or rank < chosen[0]):
                chosen = (rank, fmt, off)
        if chosen is None:
            raise ValueError("font has no supported cmap")
        _, fmt, off = chosen
        self._cmap_fmt = fmt
        if fmt == 4:
            seg_count = _u16(data, off + 6) // 2
            pos = off + 14
            ends = struct.unpack_from(f">{seg_count}H", data, pos)
            pos += seg_count * 2 + 2
            starts = struct.unpack_from(f">{seg_count}H", data, pos)
            pos += seg_count * 2
            deltas = struct.unpack_from(f">{seg_count}h", data, pos)
            pos += seg_count * 2
            range_pos = pos
            offsets = struct.unpack_from(f">{seg_count}H", data, pos)
            self._cmap4 = (starts, ends, deltas, offsets, range_pos, data)
        else:
            n = _u32(data, off + 12)
            groups = []
            pos = off + 16
            for _ in range(n):
                start, end, start_gid = struct.unpack_from(">III", data, pos)
                groups.append((start, end, start_gid))
                pos += 12
            self._cmap12 = groups

    def _parse_kern(self) -> None:
        self.kern: dict[tuple[int, int], int] = {}
        if b"kern" not in self.tables:
            return
        data = self.table(b"kern")
        if len(data) < 4:
            return
        version, ntables = struct.unpack_from(">HH", data, 0)
        if version != 0:
            return
        pos = 4
        for _ in range(ntables):
            if pos + 6 > len(data):
                break
            _ver, length, coverage = struct.unpack_from(">HHH", data, pos)
            if length < 6 or (coverage & 0xFF) != 0:
                pos += max(length, 6)
                continue
            npairs = _u16(data, pos + 6)
            pair = pos + 14
            for _i in range(npairs):
                left, right, value = struct.unpack_from(">HHh", data, pair)
                self.kern[(left, right)] = value
                pair += 6
            pos += length

    def glyph_id(self, codepoint: int) -> int:
        if self._cmap_fmt == 12:
            for start, end, gid in self._cmap12:
                if start <= codepoint <= end:
                    return gid + (codepoint - start)
            return 0
        starts, ends, deltas, offsets, range_pos, data = self._cmap4
        lo, hi = 0, len(ends) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if codepoint < starts[mid]:
                hi = mid - 1
            elif codepoint > ends[mid]:
                lo = mid + 1
            else:
                if offsets[mid] == 0:
                    return (codepoint + deltas[mid]) & 0xFFFF
                addr = range_pos + mid * 2 + offsets[mid] + 2 * (codepoint - starts[mid])
                gid = _u16(data, addr)
                if gid == 0:
                    return 0
                return (gid + deltas[mid]) & 0xFFFF
        return 0

    def outlines(self, gid: int, depth: int = 0) -> list[list[tuple[float, float]]]:
        cached = self._outlines.get(gid)
        if cached is not None:
            return cached
        if depth > 8 or gid < 0 or gid >= self.num_glyphs:
            self._outlines[gid] = []
            return []
        start = self.loca[gid]
        end = self.loca[gid + 1]
        if start == end:
            self._outlines[gid] = []
            return []
        data = self.glyf
        ncont = _s16(data, start)
        if ncont >= 0:
            result = _simple_contours(data, start)
        else:
            result = self._composite_contours(data, start, depth)
        self._outlines[gid] = result
        return result

    def _composite_contours(self, data: bytes, start: int, depth: int) -> list[list[tuple[float, float]]]:
        o = start + 10
        contours: list[list[tuple[float, float]]] = []
        while True:
            flags = _u16(data, o)
            o += 2
            child = _u16(data, o)
            o += 2
            if flags & 0x0001:
                arg1 = _s16(data, o)
                arg2 = _s16(data, o + 2)
                o += 4
            else:
                arg1 = struct.unpack_from(">b", data, o)[0]
                arg2 = struct.unpack_from(">b", data, o + 1)[0]
                o += 2
            if flags & 0x0008:
                a = d = _s16(data, o) / 16384.0
                b = c = 0.0
                o += 2
            elif flags & 0x0040:
                a = _s16(data, o) / 16384.0
                d = _s16(data, o + 2) / 16384.0
                b = c = 0.0
                o += 4
            elif flags & 0x0080:
                a = _s16(data, o) / 16384.0
                b = _s16(data, o + 2) / 16384.0
                c = _s16(data, o + 4) / 16384.0
                d = _s16(data, o + 6) / 16384.0
                o += 8
            else:
                a = d = 1.0
                b = c = 0.0
            e = float(arg1)
            f = float(arg2)
            if not (flags & 0x0002):
                e = f = 0.0
            elif flags & 0x0800:
                e, f = a * arg1 + b * arg2, c * arg1 + d * arg2
            for contour in self.outlines(child, depth + 1):
                contours.append([(a * x + b * y + e, c * x + d * y + f) for x, y in contour])
            if not (flags & 0x0020):
                break
        return contours


_ON_CURVE = 0x01
_X_SHORT = 0x02
_Y_SHORT = 0x04
_REPEAT = 0x08
_X_SAME = 0x10
_Y_SAME = 0x20


def _simple_contours(data: bytes, start: int) -> list[list[tuple[float, float]]]:
    ncont = _s16(data, start)
    o = start + 10
    ends = []
    for _ in range(ncont):
        ends.append(_u16(data, o))
        o += 2
    instr = _u16(data, o)
    o += 2 + instr
    npts = ends[-1] + 1 if ends else 0
    flags: list[int] = []
    while len(flags) < npts:
        flag = data[o]
        o += 1
        flags.append(flag)
        if flag & _REPEAT:
            rep = data[o]
            o += 1
            flags.extend([flag] * rep)
    xs: list[int] = []
    x = 0
    for flag in flags:
        if flag & _X_SHORT:
            dx = data[o]
            o += 1
            if not (flag & _X_SAME):
                dx = -dx
        elif flag & _X_SAME:
            dx = 0
        else:
            dx = _s16(data, o)
            o += 2
        x += dx
        xs.append(x)
    ys: list[int] = []
    y = 0
    for flag in flags:
        if flag & _Y_SHORT:
            dy = data[o]
            o += 1
            if not (flag & _Y_SAME):
                dy = -dy
        elif flag & _Y_SAME:
            dy = 0
        else:
            dy = _s16(data, o)
            o += 2
        y += dy
        ys.append(y)
    contours = []
    begin = 0
    for end in ends:
        pts = [(float(xs[i]), float(ys[i])) for i in range(begin, end + 1)]
        ons = [bool(flags[i] & _ON_CURVE) for i in range(begin, end + 1)]
        contours.append(_contour_to_polygon(pts, ons))
        begin = end + 1
    return contours


def _contour_to_polygon(
    pts: list[tuple[float, float]], ons: list[bool]
) -> list[tuple[float, float]]:
    """Quadratic contour to a closed polyline. The first point is not repeated."""
    if not pts:
        return []
    n = len(pts)
    expanded_pts: list[tuple[float, float]] = []
    expanded_ons: list[bool] = []
    for i in range(n):
        expanded_pts.append(pts[i])
        expanded_ons.append(ons[i])
        j = (i + 1) % n
        if not ons[i] and not ons[j]:
            expanded_pts.append(((pts[i][0] + pts[j][0]) * 0.5, (pts[i][1] + pts[j][1]) * 0.5))
            expanded_ons.append(True)
    pts = expanded_pts
    ons = expanded_ons
    if not any(ons):
        return pts
    if not ons[0]:
        k = ons.index(True)
        pts = pts[k:] + pts[:k]
        ons = ons[k:] + ons[:k]
    poly: list[tuple[float, float]] = [pts[0]]
    i = 0
    n = len(pts)
    guard = 0
    while guard <= n + 2:
        guard += 1
        nxt = (i + 1) % n
        if ons[nxt]:
            if nxt != 0:
                poly.append(pts[nxt])
            i = nxt
        else:
            end = (nxt + 1) % n
            _flatten_quad(pts[i], pts[nxt], pts[end], poly)
            if end == 0 and len(poly) > 1:
                if poly[-1] == pts[0]:
                    poly.pop()
            i = end
        if i == 0:
            break
    if len(poly) > 1 and poly[-1] == poly[0]:
        poly.pop()
    return poly


def _flatten_quad(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    out: list[tuple[float, float]],
    tol: float = 3.0,
) -> None:
    dx = p2[0] - p0[0]
    dy = p2[1] - p0[1]
    num = abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx)
    den = math.hypot(dx, dy) or 1.0
    if num / den <= tol or math.hypot(p1[0] - p0[0], p1[1] - p0[1]) < tol:
        out.append(p2)
        return
    m01 = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
    m12 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
    mid = ((m01[0] + m12[0]) * 0.5, (m01[1] + m12[1]) * 0.5)
    _flatten_quad(p0, m01, mid, out, tol)
    _flatten_quad(mid, m12, p2, out, tol)


class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, int, int]):
        self.w = width
        self.h = height
        self.buf = array("B", color * (width * height))
        self._glyph_cache: dict[tuple[int, int, int, int], tuple[bytes, int, int, int, int]] = {}
        self._coverage_lut: dict[int, bytes] = {}

    def fill_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: tuple[int, int, int],
    ) -> None:
        x0 = max(0, int(math.floor(x)))
        y0 = max(0, int(math.floor(y)))
        x1 = min(self.w, int(math.ceil(x + w)))
        y1 = min(self.h, int(math.ceil(y + h)))
        if x0 >= x1 or y0 >= y1:
            return
        row = array("B", color * (x1 - x0))
        stride = self.w * 3
        span = (x1 - x0) * 3
        for yy in range(y0, y1):
            i = yy * stride + x0 * 3
            self.buf[i : i + span] = row

    def fill_polygon(
        self,
        contours: list[list[tuple[float, float]]],
        color: tuple[int, int, int],
        samples: int = 4,
    ) -> None:
        pts = [p for c in contours for p in c]
        if len(pts) < 3:
            return
        minx = min(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        maxx = max(p[0] for p in pts)
        maxy = max(p[1] for p in pts)
        x0 = max(0, int(math.floor(minx)))
        y0 = max(0, int(math.floor(miny)))
        x1 = min(self.w, int(math.ceil(maxx)))
        y1 = min(self.h, int(math.ceil(maxy)))
        if x0 >= x1 or y0 >= y1:
            return
        shifted = [[(px - x0, py - y0) for px, py in c] for c in contours]
        cov, cw, ch = _coverage(shifted, x1 - x0, y1 - y0, samples)
        self._blit(cov, cw, ch, x0, y0, color, samples * samples)

    def fill_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        color: tuple[int, int, int],
        samples: int = 4,
        n: int = 28,
    ) -> None:
        pts = []
        for i in range(n):
            a = (math.tau * i) / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.fill_polygon([pts], color, samples)

    def text_width(self, font: Font, size: float, text: str, tracking: float = 0.0) -> float:
        scale = size / font.upem
        width = 0.0
        prev = 0
        for ch in text:
            gid = font.glyph_id(ord(ch))
            if prev and gid:
                width += font.kern.get((prev, gid), 0) * scale
            width += font.advances[gid if gid < font.num_h_metrics else -1] * scale
            width += tracking
            prev = gid
        if text:
            width -= tracking
        return width

    def wrap(
        self,
        font: Font,
        size: float,
        text: str,
        max_width: float,
        tracking: float = 0.0,
    ) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines: list[str] = []
        cur = words[0]
        for word in words[1:]:
            trial = cur + " " + word
            if self.text_width(font, size, trial, tracking) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        return lines

    def draw_text(
        self,
        font: Font,
        size: float,
        x: float,
        baseline: float,
        text: str,
        color: tuple[int, int, int],
        tracking: float = 0.0,
        samples: int = 4,
    ) -> float:
        scale = size / font.upem
        pen = x
        prev = 0
        size_key = int(round(size * 64))
        for ch in text:
            gid = font.glyph_id(ord(ch))
            if prev and gid:
                pen += font.kern.get((prev, gid), 0) * scale
            if gid:
                stamp = self._glyph_stamp(font, gid, size_key, scale, samples)
                if stamp is not None:
                    cov, gw, gh, ox, oy = stamp
                    self._blit(cov, gw, gh, int(round(pen)) + ox, int(round(baseline)) + oy, color, samples * samples)
            adv_gid = gid if gid < font.num_h_metrics else font.num_h_metrics - 1
            pen += font.advances[adv_gid] * scale + tracking
            prev = gid
        if text:
            pen -= tracking
        return pen

    def draw_text_centered(
        self,
        font: Font,
        size: float,
        cx: float,
        baseline: float,
        text: str,
        color: tuple[int, int, int],
        tracking: float = 0.0,
        samples: int = 4,
    ) -> None:
        w = self.text_width(font, size, text, tracking)
        self.draw_text(font, size, cx - w / 2, baseline, text, color, tracking, samples)

    def draw_wrapped(
        self,
        font: Font,
        size: float,
        x: float,
        y: float,
        text: str,
        color: tuple[int, int, int],
        max_width: float,
        leading: float,
        tracking: float = 0.0,
        samples: int = 3,
    ) -> float:
        """Draw wrapped text. `y` is the top of the em box. Returns the next y."""
        lines = self.wrap(font, size, text, max_width, tracking)
        asc = font.ascent * size / font.upem
        step = size * leading
        for i, line in enumerate(lines):
            self.draw_text(font, size, x, y + asc + i * step, line, color, tracking, samples)
        return y + len(lines) * step

    def _glyph_stamp(
        self,
        font: Font,
        gid: int,
        size_key: int,
        scale: float,
        samples: int,
    ) -> tuple[bytes, int, int, int, int] | None:
        key = (id(font), gid, size_key, samples)
        hit = self._glyph_cache.get(key)
        if hit is not None:
            return hit
        contours = font.outlines(gid)
        if not contours:
            self._glyph_cache[key] = None  # type: ignore[assignment]
            return None
        polys = [[(px * scale, -py * scale) for px, py in c] for c in contours]
        pts = [p for c in polys for p in c]
        minx = min(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        maxx = max(p[0] for p in pts)
        maxy = max(p[1] for p in pts)
        ox = int(math.floor(minx)) - 1
        oy = int(math.floor(miny)) - 1
        gw = max(1, int(math.ceil(maxx)) - ox + 1)
        gh = max(1, int(math.ceil(maxy)) - oy + 1)
        shifted = [[(px - ox, py - oy) for px, py in c] for c in polys]
        cov, cw, ch = _coverage(shifted, gw, gh, samples)
        stamp = (cov, cw, ch, ox, oy)
        self._glyph_cache[key] = stamp
        return stamp

    def _blit(
        self,
        cov: bytes,
        cw: int,
        ch: int,
        dx: int,
        dy: int,
        color: tuple[int, int, int],
        full: int,
    ) -> None:
        lut = self._coverage_lut.get(full)
        if lut is None:
            # Slight gamma so thin serifs stay readable without blooming.
            lut = bytes(
                min(255, int(round((i / full) ** (1 / 1.45) * 255))) for i in range(full + 1)
            )
            self._coverage_lut[full] = lut
        r, g, b = color
        x0 = max(0, dx)
        y0 = max(0, dy)
        x1 = min(self.w, dx + cw)
        y1 = min(self.h, dy + ch)
        buf = self.buf
        stride = self.w * 3
        for yy in range(y0, y1):
            row = (yy - dy) * cw
            di = yy * stride + x0 * 3
            for xx in range(x0, x1):
                a = lut[cov[row + (xx - dx)]]
                if a == 0:
                    di += 3
                    continue
                if a == 255:
                    buf[di] = r
                    buf[di + 1] = g
                    buf[di + 2] = b
                else:
                    inv = 255 - a
                    buf[di] = (buf[di] * inv + r * a) // 255
                    buf[di + 1] = (buf[di + 1] * inv + g * a) // 255
                    buf[di + 2] = (buf[di + 2] * inv + b * a) // 255
                di += 3

    def save_png(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        stride = self.w * 3
        raw = bytearray()
        buf = self.buf
        for y in range(self.h):
            raw.append(0)
            raw.extend(buf[y * stride : (y + 1) * stride])
        compressed = zlib.compress(bytes(raw), 9)
        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")
        with open(path, "wb") as fh:
            fh.write(png)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _coverage(
    contours: list[list[tuple[float, float]]],
    width: int,
    height: int,
    samples: int,
) -> tuple[bytes, int, int]:
    sw = width * samples
    sh = height * samples
    edges = []
    for cont in contours:
        m = len(cont)
        if m < 2:
            continue
        for i in range(m):
            x0, y0 = cont[i]
            x1, y1 = cont[(i + 1) % m]
            y0s = y0 * samples
            y1s = y1 * samples
            if y0s == y1s:
                continue
            x0s = x0 * samples
            x1s = x1 * samples
            if y0s < y1s:
                edges.append((y0s, y1s, x0s, (x1s - x0s) / (y1s - y0s), 1))
            else:
                edges.append((y1s, y0s, x1s, (x0s - x1s) / (y0s - y1s), -1))
    buckets: list[list[tuple[float, float, float, float, int]]] = [[] for _ in range(sh + 1)]
    for edge in edges:
        yb = int(math.floor(edge[0]))
        if yb < 0:
            yb = 0
        if yb <= sh:
            buckets[min(yb, sh)].append(edge)
    cov = bytearray(width * height)
    active: list[tuple[float, float, float, float, int]] = []
    for y in range(sh):
        if buckets[y]:
            active.extend(buckets[y])
        scan_y = y + 0.5
        if active:
            active = [e for e in active if e[1] > scan_y]
        if not active:
            continue
        hits = []
        for y0, y1, x0, dx, wind in active:
            if scan_y < y0 or scan_y >= y1:
                continue
            hits.append((x0 + dx * (scan_y - y0), wind))
        if not hits:
            continue
        hits.sort(key=lambda item: item[0])
        winding = 0
        prev_x = 0.0
        py = y // samples
        row = py * width
        for x, wind in hits:
            if winding != 0:
                _add_span(cov, row, prev_x, x, width, samples)
            winding += wind
            prev_x = x
    return bytes(cov), width, height


def _add_span(cov: bytearray, row: int, x0: float, x1: float, width: int, samples: int) -> None:
    if x1 < x0:
        x0, x1 = x1, x0
    i0 = int(math.ceil(x0 - 0.5))
    i1 = int(math.ceil(x1 - 0.5))
    if i1 <= 0 or i0 >= width * samples:
        return
    if i0 < 0:
        i0 = 0
    limit = width * samples
    if i1 > limit:
        i1 = limit
    i = i0
    while i < i1:
        px = i // samples
        j = min(i1, (px + 1) * samples)
        if 0 <= px < width:
            cov[row + px] += j - i
        i = j
