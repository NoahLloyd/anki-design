"""Anki Design — tiny colour helpers shared by the web injection
(__init__.py) and the Qt-side palettes (settings.py, addcard.py).

Kept dependency-free so it can be imported from anywhere in the add-on
without touching Anki."""

from typing import Any, Dict, Optional, Tuple


def hex_ok(value: Any) -> str:
    """Return a normalised ``#rrggbb`` string, or ``""`` if `value` isn't a
    usable 6-digit hex colour. Used to sanitise config before it lands in
    CSS / QSS, so a typo can never break a stylesheet."""
    s = str(value or "").strip()
    if not s:
        return ""
    if not s.startswith("#"):
        s = "#" + s
    if len(s) == 4:  # #abc → #aabbcc
        s = "#" + "".join(ch * 2 for ch in s[1:])
    if len(s) != 7:
        return ""
    try:
        int(s[1:], 16)
    except ValueError:
        return ""
    return s.lower()


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of two hex colours, `t` toward `b` (0 → a, 1 → b)."""
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    t = max(0.0, min(1.0, float(t)))
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def luminance(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return (r * 299 + g * 587 + b * 114) / 1000.0 / 255.0


def derive_panel(bg: str, dark: bool) -> str:
    """The "panel" tone (today card, embed chrome) for a given page
    background. Panels sit a hair *above* the paper: lighter on dark
    themes, and on light themes lighter too — unless the paper is already
    near-white, where a lighter panel would vanish, so we nudge darker."""
    if dark:
        return mix(bg, "#ffffff", 0.045)
    if luminance(bg) > 0.96:
        return mix(bg, "#000000", 0.025)
    return mix(bg, "#ffffff", 0.5)


def background_override(cfg: Dict[str, Any], dark: bool) -> Optional[Tuple[str, str]]:
    """(paper, panel) from the user's background setting for this theme,
    or None when they're on the default paper."""
    key = "background_dark" if dark else "background_light"
    bg = hex_ok(cfg.get(key))
    if not bg:
        return None
    return bg, derive_panel(bg, dark)


def apply_background(palette: Dict[str, str], cfg: Dict[str, Any],
                     dark: bool) -> Dict[str, str]:
    """Copy of a Qt-side palette dict with paper/panel swapped for the
    user's background override (if any)."""
    ov = background_override(cfg, dark)
    if not ov:
        return palette
    out = dict(palette)
    out["paper"], out["panel"] = ov
    return out
