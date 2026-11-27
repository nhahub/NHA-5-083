# UI/UX Design Guidelines

> **Status:** Active (v0.2), a living document.
> **Last updated:** 2026-11-27

Keywords **MUST** and **SHOULD** follow their usual meaning.

## 1. Purpose and scope

This document defines the visual identity, layout behavior, data-presentation conventions, and accessibility standards for the Streamlit web presentation layer (`web/streamlit/`).

* **Scope boundary:** This guide governs *how* the interface looks, adapts, and communicates information. It does **not** mandate or restrict specific pages, features, or individual components; feature scope and architecture are governed by `docs/ARCHITECTURE.md` and the project requirements.

* **Source of truth:** `docs/CODE_STYLE.md` remains the authoritative source for technical constraints, architecture boundaries, security rules, and CI enforcement. Where any conflict arises, `docs/CODE_STYLE.md` takes precedence.

* **Working with coding agents:** Contributors and AI coding agents implementing UI screens **MUST** pair this document with Streamlit's official agent skills (installed via `streamlit skills`, matching the pinned Streamlit 1.67.x stack) so that layouts, widgets, and theming options reflect current native APIs rather than deprecated patterns.

## 2. Design direction: Editorial / Paper & Ink

The application uses an **Editorial / Paper & Ink** visual language with native **light and dark theme support**. Because the project's primary contribution is an auditable multi-source data pipeline rather than a consumer-marketing food app, the interface **SHOULD** feel like a calm, high-craft digital publication or analytical briefing (*The Economist*, *Financial Times*, *Monocle*) rather than a decorative dashboard.

### Core principles

1. **Restraint over decoration.** Follow a strict **90 / 8 / 2 color budget**: roughly 90% neutral canvas and surface tones, 8% text and structural hairlines, and 2% primary accent reserved strictly for active navigation, primary actions, and focused controls.
2. **Typography and space over boxes.** Establish visual hierarchy with font scale, serif-to-sans contrast, whitespace, and hairline dividers (`st.divider()`) rather than wrapping every element in bordered cards.
3. **Zero AI-slop aesthetics.** The interface **MUST NOT** use multi-color gradients, neon glows, glassmorphism, drop shadows, rainbow chart palettes (such as `Turbo`), decorative vanity KPI strips, or custom CSS hacks.
4. **Photo-free resilience.** Our open data sources (Zomato, Overture Maps, Foursquare OS Places, OpenStreetMap) do not provide venue photography. Every layout **MUST** look complete and balanced using typography, metadata, tables, and maps alone.

5. **Data honesty first.** Missing values, multi-currency records, source provenance, and parser fallbacks **MUST** be surfaced transparently rather than hidden or smoothed over.

## 3. Visual system and dual-theme configuration

All visual theming **MUST** live in `.streamlit/config.toml` and **MUST NOT** be injected via raw HTML or CSS (`unsafe_allow_html=True`, `st.html`, or custom components are blocked by `tests/test_architecture.py`). The sole allowlisted exception is [`web/streamlit/components/card_styles.py`](../web/streamlit/components/card_styles.py), which emits a static, zero-user-data `<style>` rule targeting `[class*='st-key-card_']` so restaurant cards sit on a subtly elevated surface (`#FFFFFF` in Light mode, `#22201D` in Dark mode) distinguishable from the main canvas.

### 3.1 Color tokens (Light and Dark)

Both themes are configured natively so users can switch between Light and Dark mode through the Streamlit app menu without breaking contrast or visual identity.

| Role | Light mode (*Warm Paper*) | Dark mode (*Warm Ink*) | Usage |
| --- | --- | --- | --- |
| Main canvas (`backgroundColor`) | `#FAF9F5` | `#171614` | Primary reading surface |
| Secondary surface (`secondaryBackgroundColor`) | `#F1EFEA` | `#22201D` | Inputs, code blocks, table headers, subtle grouped panels |
| Sidebar canvas | `#F1EFEA` | `#1D1B18` | Navigation rail; clearly separated from main content |
| Primary text (`textColor`) | `#1F1E1C` | `#EDEBE6` | High-contrast body copy and headings (WCAG AA/AAA) |
| Structural hairlines (`borderColor`) | `#DDD9D0` | `#33302B` | 1px dividers, table grids, widget outlines |
| Primary accent (`primaryColor`) | `#A63D2F` | `#C44D3D` | Active nav state, primary submit buttons, focus rings |
| Link text (`linkColor`) | `#8F3226` | `#E07A6B` | Inline links tuned for legible contrast on each surface |

### 3.2 Typography and geometry

* **Headings (`headingFont`):** `"serif"` in the main content area to give pages editorial structure and visual distinction without adding external font latency.
* **Body and controls (`font`):** `"sans-serif"` for UI controls, filters, tables, and sidebar navigation (`headingFont = "sans-serif"` in sidebar sections with bumped `headingFontSizes` and `baseFontSize = 17` for accessible scannability).
* **Tabular and technical values (`codeFont`):** `"monospace"` for coordinates, batch/run IDs, schema keys, and raw technical metadata.
* **Metric scale:** Keep `metricValueFontSize` restrained (`"1.75rem"`) so numeric callouts support the page rather than dominating the viewport.
* **Geometry:** Subtle, crisp corners (`baseRadius = "0.25rem"`, `buttonRadius = "0.25rem"`) and visible structural separation (`showSidebarBorder = true`, `showWidgetBorder = true`).

### 3.3 Reference `.streamlit/config.toml`

This configuration serves as the baseline theme and preserves the server hardening rules required by `docs/CODE_STYLE.md`:

```toml
[theme]
base = "light"
font = "sans-serif"
headingFont = "serif"
codeFont = "monospace"
baseFontSize = 17
baseFontWeight = 400
metricValueFontSize = "1.75rem"
metricValueFontWeight = 600
baseRadius = "0.25rem"
buttonRadius = "0.25rem"
showSidebarBorder = true
showWidgetBorder = true

[theme.sidebar]
headingFontSizes = ["1.5rem", "1.35rem", "1.2rem", "1.1rem", "1rem", "0.9rem"]
headingFontWeights = [700, 700, 600, 700, 600, 600]

[theme.light]
primaryColor = "#A63D2F"
backgroundColor = "#FAF9F5"
secondaryBackgroundColor = "#F1EFEA"
textColor = "#1F1E1C"
linkColor = "#8F3226"
borderColor = "#DDD9D0"
dataframeBorderColor = "#DDD9D0"
dataframeHeaderBackgroundColor = "#F1EFEA"
chartCategoricalColors = [
    "#A63D2F",
    "#1E4D3B",
    "#334155",
    "#B45309",
    "#64748B",
]

[theme.light.sidebar]
font = "sans-serif"
headingFont = "sans-serif"
backgroundColor = "#F1EFEA"
secondaryBackgroundColor = "#E6E2D9"
borderColor = "#DDD9D0"
primaryColor = "#A63D2F"
greenColor = "#1E4D3B"
orangeColor = "#B45309"

[theme.dark]
primaryColor = "#C44D3D"
backgroundColor = "#171614"
secondaryBackgroundColor = "#22201D"
textColor = "#EDEBE6"
linkColor = "#E07A6B"
borderColor = "#33302B"
dataframeBorderColor = "#33302B"
dataframeHeaderBackgroundColor = "#22201D"
chartCategoricalColors = [
    "#E07A6B",
    "#52A88A",
    "#94A3B8",
    "#E5A14B",
    "#A8A29E",
]

[theme.dark.sidebar]
font = "sans-serif"
headingFont = "sans-serif"
backgroundColor = "#1D1B18"
secondaryBackgroundColor = "#292622"
borderColor = "#33302B"
primaryColor = "#E07A6B"
greenColor = "#52A88A"
orangeColor = "#E5A14B"

[server]
enableAgentApi = false

[client]
showErrorLinks = false
```

## 4. Layout, navigation, and responsiveness

Every screen **MUST** work cleanly from mobile width (~375 px) up to desktop viewports.

* **Single entry and navigation:** Call `st.set_page_config` once in `web/streamlit/app.py` with `initial_sidebar_state="auto"`, and declare all navigation centrally with `st.navigation(pages, position="hidden")` and `st.Page`. Render the sidebar menu natively using `st.page_link(..., width="stretch")` grouped under distinct Editorial category headings (`Discover` in `primary`, `Intelligence` in `green`, `Plan & Operations` in `orange`).

* **Restaurant cards and actions:** Render venue names at accessible subheader scale (`st.subheader(..., anchor=False)`), location shorthand via `st.badge(..., icon=":material/location_on:", color="gray")`, rating and cost in a clean two-column facts row, cuisines on a single line, street address as a single ellipsized line (`wrap=False`), and a 4-button real-time action bar (`Map`, `Save`, `Compare`, `+Journey`) wired with `on_click` callbacks. Saving a venue surfaces a toast pointing users to `Journey & Compare` to add stops or compare from Saved. External `Directions` buttons belong on the **Map Explorer** interactive marker/focus detail card (plus `Data table` links) and on **Journey & Compare** stop cards rather than Explore cards.

* **In-page primary controls:** Because the sidebar collapses on small screens, primary search inputs, core filters, and primary actions **MUST** live inside the main page area rather than exclusively in the sidebar. Reserve the sidebar for navigation and lightweight global context (such as dataset attribution or version metadata).

* **Fluid sizing:** Use `width="stretch"` instead of fixed pixel widths; fixed pixel dimensions are permitted only for vertical heights (such as maps and charts).

* **Adaptive grouping:** Use `st.columns` with `wrap=True` so multi-column rows stack cleanly on phones, `st.grid` with `min_column_width` for repeating item layouts, and `st.tabs`, `st.expander`, or `st.popover` for progressive disclosure of secondary filters and dense metadata.

* **Form-batched queries:** Group interactive filter widgets that feed a single backend query inside one `st.form` so users can adjust multiple parameters without triggering unnecessary reruns or API calls.

* **Intentional card usage:** Reserve `st.container(border=True)` for discrete, repeatable records or logically grouped input forms. Avoid nested bordered containers ("box-in-a-box" layouts).

## 5. Data-honesty presentation patterns

These cross-cutting rules apply wherever the corresponding data appears across any screen in the app.

| Domain concept | Presentation rule | Rationale |
| --- | --- | --- |
| **Unrated venues (`NULL`)** | Display an explicit neutral label (e.g., `Unrated` or `No rating in source`). Never render `0`, `0.0`, or empty star icons as if the venue scored zero. | Open sources like Overture, Foursquare, and OSM provide Egypt coverage without comparable review ratings; `CODE_STYLE.md` stores unrated venues as `NULL`. |
| **Multi-currency prices** | Show the venue's original amount and ISO 4217 code (`avg_cost_for_two` + `currency_code`) as the primary value. When sorting, filtering, or comparing across countries, clearly display or note the batch-standardized USD value (`avg_cost_for_two_usd`). | Prevents misleading comparisons across currencies while keeping original source amounts intact. |
| **Source provenance & licensing** | Surface the source name and license (e.g., `Overture Maps · CDLA-Permissive 2.0`, `OpenStreetMap · ODbL`, `Foursquare · Apache 2.0`, `Zomato · CC0 1.0`) in record details and attribution areas. | License preservation and attribution are core legal and engineering obligations of the pipeline. |
| **Natural-language query interpretation** | Whenever natural-language search is used, visibly display the validated `SearchParams` extracted by the backend. If `needs_clarification` is returned (including off-topic or unsupported-location prompts), render it prominently as an `st.info` prompt. Clearly attribute whether the remote Hugging Face LLM, local Hugging Face `all-MiniLM-L6-v2` ONNX semantic hybrid, or rule-based fallback handled the query via `st.caption`. When multi-turn follow-up context (`previous_params`) is active, display a concise turn breadcrumb and a `New search` reset button. | Builds user trust in constrained extraction, supports conversational refinement, and demonstrates fault-tolerant fallback behavior. |
| **Metrics and KPIs** | Promote a number to `st.metric` only if a change in that value informs a user or operator decision. Place static metadata (e.g., last refresh timestamp, environment info) in `st.caption`. | Eliminates decorative KPI walls and keeps top-of-page vertical space focused on primary tasks. |
| **Untrusted text** | Render restaurant names, addresses, cuisines, and user queries with `st.text`, `st.dataframe`, or properly escaped Markdown; never assemble HTML strings from data. | Prevents XSS and Markdown injection from open datasets and user input. |

## 6. Maps and data visualizations

* **Theme-aware styling:** Charts **SHOULD** inherit the active `[theme.light]` or `[theme.dark]` `chartCategoricalColors` palette instead of hardcoding fixed colors or rainbow scales. For interactive maps (`st.map`, `st.pydeck_chart`, or approved chart maps), adapt the basemap style to the active theme when detectable via `st.context.theme` (e.g., light neutral basemap in light mode, dark neutral basemap in dark mode), with a safe default fallback.

* **Explicit handling of missing data:** On maps and charts encoding ratings or cost, visually distinguish unrated (`NULL`) records with a neutral muted marker and explicit tooltip text rather than dropping them silently or mapping them to zero.

* **Accessible equivalents:** Every map and chart **MUST** be paired with a tabular (`st.dataframe`) or structured text equivalent—for example via `st.tabs` or an adjacent view—and **MUST NOT** rely on color alone to convey meaning.

## 7. Iconography, microcopy, and feedback states

### Iconography

* Prefer clean typography first; add icons only when they speed up scanning (navigation items, button actions, status indicators).
* Use Streamlit's built-in monochrome Material icons (`:material/...:`, such as `:material/search:`, `:material/map:`, `:material/tune:`) so icons automatically inherit light/dark theme text colors.
* **Avoid colorful Unicode emojis** in page headings, navigation items, section titles, and buttons, as they clash with the Editorial / Paper & Ink palette.

### Microcopy

* Write concise, direct, English-default UI copy. Prefer factual titles (*"Explore Restaurants"*, *"Pipeline Status"*) over marketing slogans.

* Centralize shared user-facing strings (labels, attribution text, error templates) when reused across pages.

* Right-to-left (Arabic) UI layout remains out of scope unless preceded by a dedicated spike, due to limited Streamlit RTL support.

### Loading, empty, and error states

* **Loading:** Use `st.spinner` or Streamlit's native skeleton/status indicators on network calls through `web/streamlit/api_client.py`.

* **Empty results:** Never leave a blank canvas. Display a calm, structured message explaining why no records appeared and suggest a concrete next action (e.g., widening filters or clearing a search term).
* **API or validation errors:** Catch HTTP timeouts, validation (`422`), and rate-limit (`429`) responses from the FastAPI backend cleanly and present plain-language `st.warning` / `st.error` feedback without exposing stack traces or internal URLs.

## 8. Accessibility

Every screen **MUST** meet these baseline accessibility requirements:

* **Labels on all inputs:** Every widget has a clear, descriptive label (using `label_visibility="collapsed"` only when adjacent context makes the input's purpose unambiguous for screen readers).

* **No color-only status encoding:** Status indicators (pipeline runs, data quality flags, rating tiers) **MUST** pair color with explicit text and/or icons.

* **Contrast in both themes:** Text, buttons, links, and chart series **MUST** maintain readable contrast (WCAG AA target: >= 4.5:1 for normal text, >= 3:1 for large text and UI components) in both Light and Dark modes.
* **Keyboard and touch ergonomics:** Keep clickable controls properly spaced on 375 px touchscreens and avoid cramming more than two narrow buttons side-by-side on mobile widths.

## 9. UI review checklist (before merge)

In addition to automated `ruff`, `mypy`, `tests/test_architecture.py`, and `AppTest` smoke tests (`tests/test_streamlit_smoke.py`), every UI pull request **SHOULD** pass this manual visual check:

* [ ] Checked at **desktop width** and **phone width (~375 px)** with no horizontal overflow or clipped controls.
* [ ] Checked in both **Light mode** and **Dark mode** (including charts, maps, borders, and active states).
* [ ] Primary controls are reachable without opening the sidebar on mobile (`initial_sidebar_state="auto"`).
* [ ] Zero raw HTML/CSS injections; all styling flows from `.streamlit/config.toml`.
* [ ] Unrated records (`NULL`), multi-currency prices, and source licenses render accurately.
* [ ] Every map and chart has a table or text equivalent and does not rely on color alone.
* [ ] Untrusted strings (names, addresses, queries) render safely without HTML interpolation.

## 10. Change log

| Date | Change |
| --- | --- |
| 2026-11-23 | v0.1 created: established Editorial / Paper & Ink dual-theme design system, reference `.streamlit/config.toml`, responsive rules, data-honesty conventions, accessibility guidelines, and pre-merge UI review checklist aligned with `CODE_STYLE.md` v0.12 and `ARCHITECTURE.md` v0.4. |
| 2026-11-27 | v0.2 updated: bumped `baseFontSize = 17`, added `[theme.sidebar]` heading scale and category colors (`Discover`, `Intelligence`, `Plan & Operations`) via native `st.navigation(..., position="hidden")` + `st.page_link`, refined restaurant card layout (subheader title, location badge, 2-column facts, ellipsized address, 4-button `on_click` action bar, no `Details` dossier), added scoped static card-surface shading (`card_styles.py`), and moved `Directions` to Map Explorer marker/focus cards and Journey stops. |
