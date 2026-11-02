"""Colour tokens. Categorical order was run through the dataviz palette validator (all adjacent checks pass)."""

DARK = {
    "bg": "#050806", "panel": "#0b0f0d", "card": "#0e1311", "card2": "#121815", "border": "#1b2420", "border2": "#26322c",
    "text": "#eef3f0", "text2": "#a5b2ab", "muted": "#6b7973",
    "accent": "#22c58b", "accent2": "#1a9a6c", "accent_soft": "rgba(34,197,139,0.14)", "glow": "rgba(34,197,139,0.20)",
    "pos": "#2ed88f", "neg": "#ff5d5d", "warn": "#f5b942", "grid": "rgba(255,255,255,0.07)",
    # validated order: aqua-green, yellow, blue, magenta, violet, orange
    "cat": ["#199e70", "#c98500", "#3987e5", "#d55181", "#9085e9", "#d95926"],
    "hi": "#22c58b", "lime": "#d6f23d",
    "seq": ["#0e2a20", "#14513b", "#1a7a58", "#22c58b", "#8be8c1"],
    "mode": "dark",
}
LIGHT = {
    "bg": "#f3f6f4", "panel": "#ffffff", "card": "#ffffff", "card2": "#f6f9f7", "border": "#e0e8e3", "border2": "#cfdad3",
    "text": "#0d1512", "text2": "#46544d", "muted": "#7a8881",
    "accent": "#0f9d6a", "accent2": "#0b7a53", "accent_soft": "rgba(15,157,106,0.10)", "glow": "rgba(15,157,106,0.12)",
    "pos": "#0f9d6a", "neg": "#d63a3a", "warn": "#b97a00", "grid": "rgba(0,0,0,0.07)",
    "cat": ["#1baf7a", "#eda100", "#2a78d6", "#e87ba4", "#6250d6", "#eb6834"],
    "hi": "#0f9d6a", "lime": "#9bb800",
    "seq": ["#dff5ea", "#a9e4c9", "#5fcb9d", "#1ea575", "#0b6e4b"],
    "mode": "light",
}


def tokens(mode: str) -> dict:
    return DARK if mode == "dark" else LIGHT
