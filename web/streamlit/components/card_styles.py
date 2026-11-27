"""Scoped static CSS helper for distinguishable restaurant card surfaces."""

from __future__ import annotations

import streamlit as st

from web.streamlit.constants import (
    COLOR_CARD_SURFACE_DARK,
    COLOR_CARD_SURFACE_LIGHT,
)


def inject_card_surface_style() -> None:
    """Apply subtle theme-aware background shading to `.st-key-card_*` containers."""
    try:
        is_dark = getattr(st.context.theme, "type", None) == "dark"
    except RuntimeError:
        is_dark = False
    bg = COLOR_CARD_SURFACE_DARK if is_dark else COLOR_CARD_SURFACE_LIGHT
    st.html(f"<style>[class*='st-key-card_'] {{ background-color: {bg}; }}</style>")
