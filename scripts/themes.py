"""Editorial theme registry for Miseform reading editions.

Five selectable themes share one underlying recipe card and one render
pipeline. A theme is a real visual system -- color, typography, density
and layout rules -- that applies to the HTML reading edition, the PDF
printed from it, and the Excel workbook. Themes never change the recipe
data: weights, volumes, percentages, method steps and blockers are
identical in every theme, and every theme carries the same functional
tables (ingredient weight / volume / scaling %, staged numbered method,
yield, source notes, assembly cards).

Theme ids are stable strings. "original" is the approved rust/cream
default and is also the compatible default for records that predate
this field; old records keep their current look unless a theme is
explicitly selected.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THEME = "original"

# Ordered list of every theme id the toolchain may render. The first one
# is the default for records without an explicit selection.
THEME_IDS = ("original", "paper", "atelier", "service", "ledger")

THEME_NAMES = {
    "original": "Miseform Original",
    "paper": "Paper",
    "atelier": "Atelier",
    "service": "Service",
    "ledger": "Ledger",
}

THEME_DESCRIPTIONS = {
    "original": (
        "Approved rust/cream editorial default. Warm white paper, near-black "
        "body text, clay accent, expressive serif titles and generous whitespace."
    ),
    "paper": (
        "Minimal black/white edition. No accent color, quiet gray labels, "
        "extra whitespace and a single-column reading rhythm suited to "
        "photocopying and line-cook stations."
    ),
    "atelier": (
        "Restrained teal editorial edition. Teal ink and rules, cool paper "
        "tone, slightly tighter facts strip for a composed, gallery-ready "
        "reading card."
    ),
    "service": (
        "High-contrast compact kitchen edition. Black rules, compact spacing, "
        "smaller type and a red alert accent for the line, built to survive "
        "a busy station."
    ),
    "ledger": (
        "Precise tabular prep edition. Full table grid, tabular figures, "
        "visible headers and tight rows built around the ingredient table "
        "and batch-scaling math."
    ),
}


@dataclass(frozen=True)
class XlsxPalette:
    """Color and typography values for one theme's Excel workbook."""

    title: str  # title font color
    accent: str
    ink: str
    muted: str
    rule: str
    pale: str  # group heading / total fill
    status_fill: str
    status_text: str
    input_fill: str  # editable batch-factor cell fill
    caption: str  # note / source text color
    tab: str  # sheet tab color
    gridlines: bool  # worksheet grid visible
    title_font: str
    body_font: str


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    css_file: str | None  # templates/themes/<id>.css; None = base stylesheet only
    xlsx: XlsxPalette

    def xlsx_colors(self) -> dict[str, str]:
        return {
            "title": self.xlsx.title,
            "accent": self.xlsx.accent,
            "ink": self.xlsx.ink,
            "muted": self.xlsx.muted,
            "rule": self.xlsx.rule,
            "pale": self.xlsx.pale,
            "status_fill": self.xlsx.status_fill,
            "status_text": self.xlsx.status_text,
            "input_fill": self.xlsx.input_fill,
            "caption": self.xlsx.caption,
            "tab": self.xlsx.tab,
        }


# ------------------------------------------------------------------ palettes

_ORIGINAL = XlsxPalette(
    title="23231F",
    accent="A0442D",
    ink="23231F",
    muted="68685F",
    rule="DEDED5",
    pale="F7F4EE",
    status_fill="FBF1E6",
    status_text="8A3A22",
    input_fill="FFF0B3",
    caption="57645E",
    tab="A0442D",
    gridlines=False,
    title_font="Georgia",
    body_font="Arial",
)

_PAPER = XlsxPalette(
    title="1A1A1A",
    accent="1A1A1A",
    ink="1A1A1A",
    muted="595959",
    rule="BFBFBF",
    pale="FFFFFF",
    status_fill="F2F2F2",
    status_text="1A1A1A",
    input_fill="FFFFFF",
    caption="4D4D4D",
    tab="1A1A1A",
    gridlines=False,
    title_font="Georgia",
    body_font="Arial",
)

_ATELIER = XlsxPalette(
    title="1F3A3A",
    accent="2E6E6E",
    ink="1F3A3A",
    muted="4A6B6B",
    rule="B9CFCF",
    pale="E8F2F2",
    status_fill="DCE9E9",
    status_text="1F3A3A",
    input_fill="E3EFEF",
    caption="4A6B6B",
    tab="2E6E6E",
    gridlines=False,
    title_font="Georgia",
    body_font="Arial",
)

_SERVICE = XlsxPalette(
    title="000000",
    accent="B00020",
    ink="000000",
    muted="333333",
    rule="000000",
    pale="F5F5F5",
    status_fill="FDEDED",
    status_text="B00020",
    input_fill="FFF0F0",
    caption="333333",
    tab="B00020",
    gridlines=False,
    title_font="Georgia",
    body_font="Arial",
)

_LEDGER = XlsxPalette(
    title="1A1A1A",
    accent="4A4A4A",
    ink="1A1A1A",
    muted="555555",
    rule="8A8A8A",
    pale="F2F2F2",
    status_fill="E8E8E8",
    status_text="1A1A1A",
    input_fill="FFFFFF",
    caption="555555",
    tab="4A4A4A",
    gridlines=True,
    title_font="Arial",
    body_font="Arial",
)

THEMES: dict[str, Theme] = {
    "original": Theme("original", "Miseform Original", None, _ORIGINAL),
    "paper": Theme("paper", "Paper", "paper.css", _PAPER),
    "atelier": Theme("atelier", "Atelier", "atelier.css", _ATELIER),
    "service": Theme("service", "Service", "service.css", _SERVICE),
    "ledger": Theme("ledger", "Ledger", "ledger.css", _LEDGER),
}


def theme(theme_id: str) -> Theme:
    """Return the registered theme for ``theme_id``, or raise KeyError."""
    if theme_id not in THEMES:
        raise KeyError(f"unknown theme {theme_id!r}; expected one of {THEME_IDS}")
    return THEMES[theme_id]

__all__ = [
    "DEFAULT_THEME",
    "THEME_IDS",
    "THEME_NAMES",
    "THEME_DESCRIPTIONS",
    "Theme",
    "XlsxPalette",
    "THEMES",
    "theme",
]
