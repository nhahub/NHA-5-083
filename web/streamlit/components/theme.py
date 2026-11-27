"""Shared design system tokens and global stylesheet injection for Streamlit."""

from __future__ import annotations

import streamlit as st

THEME_TOKENS: dict[str, str] = {
    "bg_canvas": "#060A13",
    "bg_sidebar": "#0A0F1C",
    "bg_surface": "#0F1523",
    "bg_surface_elevated": "#141C2E",
    "bg_form": "#0B111E",
    "bg_input": "#171E2E",
    "bg_button_secondary": "#161C29",
    "bg_button_secondary_hover": "#1E2638",
    "border_subtle": "#1E293B",
    "border_input": "#2A3548",
    "border_accent": "rgba(240, 109, 29, 0.55)",
    "text_primary": "#F8FAFC",
    "text_secondary": "#CBD5E1",
    "text_muted": "#94A3B8",
    "accent_orange": "#F06D1D",
    "accent_orange_hover": "#DF5B0D",
    "accent_orange_active": "#C74E08",
    "accent_cyan": "#38BDF8",
    "accent_cyan_strong": "#0384C6",
    "accent_emerald": "#34D399",
    "accent_amber": "#F59E0B",
    "accent_rose": "#F87171",
    "radius_sm": "6px",
    "radius_md": "8px",
    "radius_lg": "14px",
    "radius_pill": "999px",
    "shadow_card": "0 6px 20px rgba(2, 6, 23, 0.42)",
    "shadow_hero": "0 10px 30px rgba(2, 6, 23, 0.55)",
    "focus_ring": "0 0 0 2px rgba(240, 109, 29, 0.45)",
    "font_sans": (
        "'Inter', 'Plus Jakarta Sans', system-ui, -apple-system, "
        "'Segoe UI', Roboto, sans-serif"
    ),
    "font_mono": "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
}


def build_theme_css() -> str:
    """Build the complete global CSS stylesheet from shared THEME_TOKENS."""
    t = THEME_TOKENS
    return f"""
<style>
:root {{
    --es-bg-canvas: {t['bg_canvas']};
    --es-bg-sidebar: {t['bg_sidebar']};
    --es-bg-surface: {t['bg_surface']};
    --es-bg-surface-elevated: {t['bg_surface_elevated']};
    --es-bg-form: {t['bg_form']};
    --es-bg-input: {t['bg_input']};
    --es-bg-btn-sec: {t['bg_button_secondary']};
    --es-bg-btn-sec-hover: {t['bg_button_secondary_hover']};
    --es-border-subtle: {t['border_subtle']};
    --es-border-input: {t['border_input']};
    --es-border-accent: {t['border_accent']};
    --es-text-primary: {t['text_primary']};
    --es-text-secondary: {t['text_secondary']};
    --es-text-muted: {t['text_muted']};
    --es-accent-orange: {t['accent_orange']};
    --es-accent-orange-hover: {t['accent_orange_hover']};
    --es-accent-orange-active: {t['accent_orange_active']};
    --es-accent-cyan: {t['accent_cyan']};
    --es-accent-cyan-strong: {t['accent_cyan_strong']};
    --es-accent-emerald: {t['accent_emerald']};
    --es-accent-amber: {t['accent_amber']};
    --es-accent-rose: {t['accent_rose']};
    --es-radius-sm: {t['radius_sm']};
    --es-radius-md: {t['radius_md']};
    --es-radius-lg: {t['radius_lg']};
    --es-radius-pill: {t['radius_pill']};
    --es-shadow-card: {t['shadow_card']};
    --es-shadow-hero: {t['shadow_hero']};
    --es-focus-ring: {t['focus_ring']};
    --es-font-sans: {t['font_sans']};
    --es-font-mono: {t['font_mono']};
}}

/* Global canvas and typography */
html, body, [data-testid="stAppViewContainer"], .stApp {{
    font-family: var(--es-font-sans);
    color: var(--es-text-primary);
}}

[data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(
            900px 420px at 88% 0%,
            rgba(240, 109, 29, 0.08),
            transparent 62%
        ),
        radial-gradient(
            760px 380px at 10% 10%,
            rgba(3, 132, 198, 0.09),
            transparent 60%
        ),
        var(--es-bg-canvas);
}}

[data-testid="stHeader"] {{
    background: rgba(6, 10, 19, 0.82);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(30, 41, 59, 0.6);
}}

[data-testid="stMainBlockContainer"] {{
    padding-top: 4.25rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: var(--es-font-sans);
    color: var(--es-text-primary);
    letter-spacing: -0.02em;
}}

code, pre {{
    font-family: var(--es-font-mono);
}}

hr, [data-testid="stDivider"] {{
    border-color: var(--es-border-subtle);
}}

/* Sidebar shell and navigation */
[data-testid="stSidebar"] {{
    background-color: var(--es-bg-sidebar);
    border-right: 1px solid var(--es-border-subtle);
}}

[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{
    color: var(--es-text-muted);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
}}

[data-testid="stSidebarNavLink"] {{
    background-color: var(--es-bg-btn-sec);
    border: 1px solid var(--es-border-input);
    border-radius: var(--es-radius-md);
    padding: 0.45rem 0.75rem;
    margin-bottom: 0.35rem;
    color: var(--es-text-secondary);
    transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease;
}}

[data-testid="stSidebarNavLink"]:hover {{
    background-color: var(--es-bg-btn-sec-hover);
    border-color: var(--es-border-accent);
    color: var(--es-text-primary);
}}

[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background-color: var(--es-accent-orange);
    border-color: var(--es-accent-orange);
    color: #FFFFFF;
    font-weight: 600;
    box-shadow: 0 4px 14px rgba(240, 109, 29, 0.28);
}}

[data-testid="stSidebarNavLink"][aria-current="page"] span,
[data-testid="stSidebarNavLink"][aria-current="page"] svg {{
    color: #FFFFFF;
    fill: #FFFFFF;
}}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    color: var(--es-text-muted);
}}

[data-testid="stSidebar"] [data-testid="stElementContainer"]:last-child [data-testid="stCaptionContainer"] {{
    background: rgba(16, 185, 129, 0.09);
    border: 1px solid rgba(52, 211, 153, 0.28);
    border-radius: var(--es-radius-md);
    padding: 0.45rem 0.65rem;
    color: var(--es-accent-emerald);
}}

/* Page hero banner container */
.st-key-page_hero {{
    background: linear-gradient(
        118deg,
        rgba(240, 109, 29, 0.16) 0%,
        var(--es-bg-surface) 44%,
        #0B1222 100%
    );
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-lg);
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.15rem;
    box-shadow: var(--es-shadow-hero);
}}

.st-key-page_hero h1 {{
    font-size: clamp(1.6rem, 2.6vw, 2.25rem);
    font-weight: 700;
    margin: 0 0 0.35rem 0;
    line-height: 1.18;
    color: var(--es-text-primary);
}}

.st-key-page_hero [data-testid="stCaptionContainer"] p {{
    color: var(--es-text-muted);
    font-size: 0.94rem;
    margin: 0;
}}

/* Destination profile accent card */
.st-key-destination_profile_card {{
    background: linear-gradient(
        115deg,
        rgba(240, 109, 29, 0.18) 0%,
        var(--es-bg-surface) 50%,
        #0C1324 100%
    );
    border: 1px solid var(--es-border-subtle);
    border-left: 4px solid var(--es-accent-orange);
    border-radius: var(--es-radius-lg);
    padding: 1.35rem 1.6rem;
    margin: 0.75rem 0 1rem 0;
    box-shadow: var(--es-shadow-card);
}}

.st-key-destination_profile_card h2 {{
    margin-top: 0;
    color: var(--es-text-primary);
}}

/* Filter forms and panels */
[data-testid="stForm"] {{
    background-color: var(--es-bg-form);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-lg);
    padding: 1.25rem 1.35rem;
    box-shadow: var(--es-shadow-card);
}}

/* Form controls, inputs, dropdowns, sliders */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {{
    background-color: var(--es-bg-input);
    border-color: var(--es-border-input);
    border-radius: var(--es-radius-md);
    color: var(--es-text-primary);
}}

[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {{
    color: var(--es-text-muted);
}}

[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-baseweb="select"] > div:focus-within {{
    border-color: var(--es-accent-orange);
    box-shadow: var(--es-focus-ring);
    outline: none;
}}

[data-baseweb="popover"] ul,
[data-baseweb="menu"] {{
    background-color: var(--es-bg-surface-elevated);
    border: 1px solid var(--es-border-input);
    border-radius: var(--es-radius-md);
}}

[data-baseweb="tag"] {{
    background-color: rgba(240, 109, 29, 0.16);
    border: 1px solid rgba(240, 109, 29, 0.38);
    color: var(--es-text-primary);
    border-radius: var(--es-radius-pill);
}}

/* Buttons and link buttons */
button[kind="primary"],
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {{
    background-color: var(--es-accent-orange);
    border: 1px solid var(--es-accent-orange);
    color: #FFFFFF;
    font-weight: 600;
    border-radius: var(--es-radius-md);
    transition: background-color 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}}

button[kind="primary"]:hover:not(:disabled),
button[data-testid="stBaseButton-primary"]:hover:not(:disabled),
button[data-testid="stBaseButton-primaryFormSubmit"]:hover:not(:disabled) {{
    background-color: var(--es-accent-orange-hover);
    border-color: var(--es-accent-orange-hover);
    box-shadow: 0 4px 14px rgba(240, 109, 29, 0.3);
}}

button[kind="primary"]:active:not(:disabled),
button[data-testid="stBaseButton-primary"]:active:not(:disabled),
button[data-testid="stBaseButton-primaryFormSubmit"]:active:not(:disabled) {{
    background-color: var(--es-accent-orange-active);
    border-color: var(--es-accent-orange-active);
}}

button[kind="secondary"],
button[data-testid="stBaseButton-secondary"],
[data-testid="stLinkButton"] a {{
    background-color: var(--es-bg-btn-sec);
    border: 1px solid var(--es-border-input);
    color: var(--es-text-primary);
    border-radius: var(--es-radius-md);
    transition: background-color 150ms ease, border-color 150ms ease;
}}

button[kind="secondary"]:hover:not(:disabled),
button[data-testid="stBaseButton-secondary"]:hover:not(:disabled),
[data-testid="stLinkButton"] a:hover {{
    background-color: var(--es-bg-btn-sec-hover);
    border-color: var(--es-border-accent);
    color: var(--es-text-primary);
}}

button:focus-visible,
a:focus-visible,
[role="tab"]:focus-visible {{
    outline: 2px solid var(--es-accent-orange);
    outline-offset: 2px;
    box-shadow: var(--es-focus-ring);
}}

button:disabled {{
    opacity: 0.45;
    cursor: not-allowed;
}}

/* Bordered cards and restaurant containers */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-lg);
    box-shadow: var(--es-shadow-card);
    transition: border-color 160ms ease, box-shadow 160ms ease;
}}

[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    border-color: var(--es-border-accent);
}}

/* KPI metric cards */
[data-testid="stMetric"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-lg);
    padding: 1rem 1.15rem;
    box-shadow: var(--es-shadow-card);
}}

[data-testid="stMetricLabel"] p {{
    color: var(--es-text-muted);
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}

[data-testid="stMetricValue"] {{
    color: var(--es-text-primary);
    font-weight: 700;
    letter-spacing: -0.02em;
}}

[data-testid="stMetricDelta"] {{
    color: var(--es-accent-cyan);
}}

/* Tabs and segmented controls */
[data-testid="stTabs"] [role="tablist"] {{
    border-bottom: 1px solid var(--es-border-subtle);
    gap: 0.35rem;
}}

[data-testid="stTabs"] [role="tab"] {{
    color: var(--es-text-muted);
    font-weight: 500;
    border-radius: var(--es-radius-sm) var(--es-radius-sm) 0 0;
    padding: 0.45rem 0.9rem;
}}

[data-testid="stTabs"] [role="tab"]:hover {{
    color: var(--es-text-primary);
}}

[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
    color: var(--es-text-primary);
    border-bottom-color: var(--es-accent-orange);
}}

[data-testid="stSegmentedControl"] button {{
    background-color: var(--es-bg-btn-sec);
    border-color: var(--es-border-input);
    color: var(--es-text-secondary);
}}

[data-testid="stSegmentedControl"] button[aria-pressed="true"] {{
    background-color: var(--es-accent-orange);
    border-color: var(--es-accent-orange);
    color: #FFFFFF;
    font-weight: 600;
}}

/* Expanders */
[data-testid="stExpander"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-md);
}}

/* Dataframes and static tables */
[data-testid="stDataFrame"],
[data-testid="stTable"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-md);
    overflow: hidden;
}}

[data-testid="stTable"] th {{
    background-color: var(--es-bg-surface-elevated);
    color: var(--es-text-primary);
    border-color: var(--es-border-subtle);
}}

[data-testid="stTable"] td {{
    color: var(--es-text-secondary);
    border-color: var(--es-border-subtle);
}}

/* Alerts, empty states, warnings, errors, modals, and spinners */
[data-testid="stAlert"] {{
    border-radius: var(--es-radius-md);
    border-width: 1px;
}}

[data-testid="stAlertContainer"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-subtle);
    border-radius: var(--es-radius-md);
}}

[data-testid="stDialog"] [role="dialog"] {{
    background-color: var(--es-bg-surface);
    border: 1px solid var(--es-border-input);
    border-radius: var(--es-radius-lg);
    box-shadow: var(--es-shadow-hero);
}}

[data-testid="stSpinner"] > div {{
    color: var(--es-text-secondary);
}}

/* Responsive adjustments for tablet and mobile */
@media (max-width: 1024px) {{
    [data-testid="stMainBlockContainer"] {{
        padding-left: 1.25rem;
        padding-right: 1.25rem;
    }}

    .st-key-page_hero {{
        padding: 1.2rem 1.35rem;
    }}
}}

@media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{
        padding-top: 3.75rem;
        padding-left: 0.85rem;
        padding-right: 0.85rem;
    }}

    .st-key-page_hero,
    .st-key-destination_profile_card {{
        padding: 1rem 1.1rem;
        border-radius: 12px;
    }}

    [data-testid="stForm"] {{
        padding: 0.95rem 1rem;
    }}

    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primaryFormSubmit"],
    [data-testid="stLinkButton"] a {{
        min-height: 40px;
    }}
}}
</style>
"""


def inject_theme_css() -> None:
    """Inject the global design-system stylesheet once per Streamlit run."""
    st.markdown(build_theme_css(), unsafe_allow_html=True)
