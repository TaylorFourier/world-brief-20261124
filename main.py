"""World brief for Tuesday 24 November 2026.

Draws one 1024x1024 PNG from reports published that day. The Hormuz
account is an IRGC claim and is labeled as not independently confirmed.
Nothing here is fetched at runtime.

Run: python3 main.py
Writes: /output/entry.png
"""

from __future__ import annotations

import os
import sys

# The grader runs `python3 -P -s /bot/main.py`, which does not put
# the script directory on sys.path, so a bare sibling import fails.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render import Canvas, Font

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"), "entry.png")

PAPER = (246, 241, 232)
INK = (24, 21, 18)
MUTED = (92, 84, 74)
CRIMSON = (164, 38, 32)
CREAM = (255, 250, 242)
SEA = (20, 61, 78)
LAND = (214, 196, 160)
LAND_EDGE = (168, 144, 104)
HULL = (32, 30, 28)
CABIN = (58, 54, 48)
FLAME = (222, 92, 28)
FLAME_HOT = (246, 196, 78)
RULE = (24, 21, 18)
HAIR = (196, 184, 166)
CARD = (252, 248, 241)
BLUE = (30, 74, 112)
GREEN = (26, 102, 72)
GOLD = (154, 104, 36)

W = 1024
H = 1024


def load_fonts() -> tuple[Font, Font, Font]:
    serif = Font(os.path.join(ROOT, "fonts", "LiberationSerif-Bold.ttf"))
    sans_b = Font(os.path.join(ROOT, "fonts", "LiberationSans-Bold.ttf"))
    sans = Font(os.path.join(ROOT, "fonts", "LiberationSans-Regular.ttf"))
    return serif, sans_b, sans


def double_rule(c: Canvas, x: float, y: float, w: float, heavy: int = 3) -> float:
    c.fill_rect(x, y, w, heavy, RULE)
    c.fill_rect(x, y + heavy + 3, w, 1, RULE)
    return y + heavy + 4


def tanker(c: Canvas, x: float, y: float) -> None:
    hull = [
        (x - 24, y - 3),
        (x + 16, y - 6),
        (x + 26, y),
        (x + 16, y + 6),
        (x - 24, y + 4),
        (x - 28, y + 1),
    ]
    cabin = [
        (x - 4, y - 5),
        (x + 8, y - 5),
        (x + 8, y - 15),
        (x - 2, y - 15),
        (x - 4, y - 11),
    ]
    c.fill_polygon([hull], HULL, samples=4)
    c.fill_polygon([cabin], CABIN, samples=4)
    c.fill_circle(x - 1, y - 22, 6.5, FLAME, samples=4)
    c.fill_circle(x, y - 28, 4.2, FLAME_HOT, samples=4)


def number_badge(c: Canvas, font: Font, x: float, y: float, n: str) -> None:
    c.fill_circle(x, y, 8, CREAM, samples=4)
    c.draw_text_centered(font, 12, x, y + 4.2, n, INK, samples=4)


def hormuz_diagram(c: Canvas, font: Font, sans_b: Font, x: float, y: float, w: float, h: float) -> None:
    c.fill_rect(x, y, w, h, SEA)
    # Iran, the northern shore. The coast bends south into the strait.
    iran = [
        (x, y),
        (x + w, y),
        (x + w, y + 50),
        (x + 860, y + 56),
        (x + 740, y + 70),
        (x + 640, y + 86),
        (x + 560, y + 94),
        (x + 470, y + 84),
        (x + 360, y + 62),
        (x + 220, y + 56),
        (x + 80, y + 68),
        (x, y + 60),
    ]
    # Oman and the Musandam peninsula, which makes the narrows.
    oman = [
        (x, y + h - 28),
        (x, y + 146),
        (x + 50, y + 154),
        (x + 170, y + 148),
        (x + 300, y + 158),
        (x + 420, y + 152),
        (x + 500, y + 136),
        (x + 542, y + 114),
        (x + 590, y + 138),
        (x + 700, y + 148),
        (x + 820, y + 156),
        (x + w, y + 164),
        (x + w, y + h - 28),
    ]
    c.fill_polygon([iran], LAND, samples=4)
    c.fill_polygon([oman], LAND, samples=4)
    c.draw_text(sans_b, 13, x + 22, y + 32, "IRAN", INK, tracking=1.4, samples=3)
    c.draw_text(sans_b, 13, x + 22, y + h - 50, "UAE", INK, tracking=1.4, samples=3)
    c.draw_text(sans_b, 13, x + 470, y + h - 50, "OMAN", INK, tracking=1.4, samples=3)
    c.draw_text(sans_b, 12, x + 28, y + 112, "PERSIAN GULF", CREAM, tracking=1.1, samples=3)
    gulf = "GULF OF OMAN"
    gulf_w = c.text_width(sans_b, 12, gulf, tracking=1.1)
    c.draw_text(sans_b, 12, x + w - 18 - gulf_w, y + 132, gulf, CREAM, tracking=1.1, samples=3)

    # Positions as the IRGC described them: one near the southern coast,
    # two in the eastern strait. A diagram, not a confirmed location.
    ships = [(418, 134, "1"), (648, 112, "2"), (748, 104, "3")]
    for sx, sy, n in ships:
        tanker(c, x + sx, y + sy)
        number_badge(c, sans_b, x + sx - 34, y + sy + 2, n)

    c.fill_rect(x, y + h - 28, w, 28, CRIMSON)
    label = "DIAGRAM  ·  POSITIONS AS THE IRGC DESCRIBED THEM  ·  NOT CONFIRMED"
    c.draw_text_centered(sans_b, 13, x + w / 2, y + h - 9, label, CREAM, tracking=0.7, samples=3)


def chessboard(c: Canvas, x: float, y: float, cell: int = 8) -> None:
    light = (236, 214, 176)
    dark = (92, 58, 42)
    for row in range(8):
        for col in range(8):
            color = light if (row + col) % 2 == 0 else dark
            c.fill_rect(x + col * cell, y + row * cell, cell, cell, color)
    c.fill_rect(x - 2, y - 2, cell * 8 + 4, 2, INK)
    c.fill_rect(x - 2, y + cell * 8, cell * 8 + 4, 2, INK)
    c.fill_rect(x - 2, y - 2, 2, cell * 8 + 4, INK)
    c.fill_rect(x + cell * 8, y - 2, 2, cell * 8 + 4, INK)


def stat_box(c: Canvas, serif: Font, sans_b: Font, x: float, y: float, w: float, h: float, kicker: str, value: str) -> None:
    c.fill_rect(x, y, w, h, INK)
    c.draw_text(sans_b, 12, x + 14, y + 20, kicker, GOLD, tracking=1.2, samples=3)
    c.draw_text(serif, 26, x + 14, y + 52, value, CREAM, samples=4)


def draw_card(
    c: Canvas,
    serif: Font,
    sans_b: Font,
    sans: Font,
    x: float,
    y: float,
    w: float,
    h: float,
    accent: tuple[int, int, int],
    index: str,
    kicker: str,
    headline: str,
    body: str,
    source: str,
    board: bool = False,
) -> None:
    c.fill_rect(x, y, w, h, CARD)
    c.fill_rect(x, y, w, 6, accent)
    c.fill_rect(x, y + h - 1, w, 1, HAIR)
    c.fill_rect(x, y, 1, h, HAIR)
    c.fill_rect(x + w - 1, y, 1, h, HAIR)
    pad = 14
    inner = w - pad * 2
    c.draw_text(sans_b, 12, x + pad, y + 28, f"{index}    {kicker}", accent, tracking=0.8, samples=3)
    text_bottom = c.draw_wrapped(serif, 20, x + pad, y + 36, headline, INK, inner, 1.04, samples=4)
    body_top = text_bottom + 8
    if board:
        cell = 8
        board_w = cell * 8
        c.draw_wrapped(sans, 15, x + pad, body_top, body, INK, inner - board_w - 12, 1.28, samples=3)
        chessboard(c, x + w - pad - board_w, body_top + 2, cell)
    else:
        c.draw_wrapped(sans, 15, x + pad, body_top, body, INK, inner, 1.28, samples=3)
    c.draw_text(sans_b, 12, x + pad, y + h - 16, source, MUTED, tracking=0.6, samples=3)


def build() -> Canvas:
    serif, sans_b, sans = load_fonts()
    c = Canvas(W, H, PAPER)

    c.fill_rect(0, 0, W, 8, CRIMSON)

    margin = 32
    content_w = W - margin * 2
    y = 20
    y = double_rule(c, margin, y, content_w, heavy=4)
    c.draw_text_centered(serif, 58, W / 2, y + 62, "WORLD BRIEF", INK, samples=4)
    c.draw_text_centered(
        sans_b,
        18,
        W / 2,
        y + 96,
        "TUESDAY  24 NOVEMBER  2026",
        CRIMSON,
        tracking=1.6,
        samples=3,
    )
    c.draw_text_centered(
        sans,
        14,
        W / 2,
        y + 122,
        "PERSIAN GULF    ·    EAST ASIA    ·    GAZA    ·    GENEVA",
        MUTED,
        tracking=0.8,
        samples=3,
    )
    y = double_rule(c, margin, y + 136, content_w, heavy=4)

    y += 16
    c.draw_text(sans_b, 13, margin, y + 14, "LEAD    ·    PERSIAN GULF    ·    MARITIME", CRIMSON, tracking=1.1, samples=3)
    y += 22
    headline = "Iran says three oil tankers hit mines and catch fire in the Strait of Hormuz"
    y = c.draw_wrapped(serif, 40, margin, y, headline, INK, content_w, 1.02, samples=4)
    y += 8
    dek = (
        "The IRGC, via Iranian state media, said one tanker was near the southern coast "
        "and two were in the eastern strait, and that U.S. military air cover and escort "
        "did not prevent the explosions. The claim was reported Tuesday and has not been "
        "independently confirmed."
    )
    y = c.draw_wrapped(sans, 17, margin, y, dek, INK, content_w, 1.28, samples=3)
    y += 6
    c.draw_text(
        sans,
        13,
        margin,
        y + 14,
        "Reported Tuesday by CNBC, Anadolu Agency and Al Jazeera. Iran International said the claim could not be independently verified.",
        MUTED,
        samples=3,
    )
    y += 28
    hormuz_diagram(c, sans, sans_b, margin, y, content_w, 214)
    y += 214 + 12

    gap = 12
    box_w = (content_w - gap * 2) / 3
    box_h = 64
    stat_box(c, serif, sans_b, margin, y, box_w, box_h, "BRENT", "near $89")
    stat_box(c, serif, sans_b, margin + box_w + gap, y, box_w, box_h, "WTI", "near $80")
    stat_box(c, serif, sans_b, margin + (box_w + gap) * 2, y, box_w, box_h, "FUTURES", "inched lower")
    c.draw_text(sans, 12, margin, y + box_h + 16, "Oil futures on Tuesday, as reported by CNBC. Figures are approximate.", MUTED, samples=3)
    y += box_h + 28

    cards_h = 1024 - 36 - y - 8
    card_w = (content_w - gap * 2) / 3
    cards = [
        (
            BLUE,
            "01",
            "EAST ASIA",
            "Russian warplanes enter South Korea's air-defense zone",
            "Several Russian military aircraft entered the KADIZ near Ulleung Island early Tuesday. Seoul scrambled jets. The Joint Chiefs said sovereign airspace was not violated. A shelter alert was issued, then lifted. Seoul said it would summon Russia's defense attaché.",
            "YONHAP   ·   THE GUARDIAN",
            False,
        ),
        (
            CRIMSON,
            "02",
            "GAZA",
            "Drone strike in Khan Younis kills three, medics say",
            "An Israeli drone strike early Tuesday hit a police post in Al-Mawasi, west of Khan Younis, killing three Palestinians and wounding five, according to medical sources and the Palestinian news agency WAFA.",
            "ANADOLU   ·   WAFA",
            False,
        ),
        (
            GREEN,
            "03",
            "GENEVA",
            "Youngest world chess championship match opens in Geneva",
            "Defending champion Gukesh of India faces Javokhir Sindarov of Uzbekistan. Both players are 20. Game 1 is scheduled Tuesday at 15:00 in Cologny, Geneva.",
            "FIDE   ·   THE HINDU",
            True,
        ),
    ]
    for i, (accent, index, kicker, title, body, source, board) in enumerate(cards):
        draw_card(
            c,
            serif,
            sans_b,
            sans,
            margin + i * (card_w + gap),
            y,
            card_w,
            cards_h,
            accent,
            index,
            kicker,
            title,
            body,
            source,
            board,
        )

    c.fill_rect(0, H - 32, W, 32, INK)
    c.fill_rect(0, H - 32, W, 3, CRIMSON)
    c.draw_text_centered(
        sans,
        12,
        W / 2,
        H - 12,
        "Compiled from reports published 24 November 2026.  Claims are attributed.  The Hormuz account is unconfirmed.",
        CREAM,
        samples=3,
    )
    return c


def main() -> None:
    canvas = build()
    canvas.save_png(OUT)


if __name__ == "__main__":
    main()
