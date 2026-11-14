# SIRIX — Master UI/UX Architecture & Design System Specification

**Document ID:** `00_SIRIX_MASTER_ARCHITECTURE`  
**Target Branch:** `feat/adaptive-client`  
**System Domain:** Autonomous Quantitative Swing Engine (Zero-Override Telemetry)  
**Target Clients:** Adaptive PWA (iOS/Android Mobile + Chromebook/Desktop Web)  

---

## 1. Executive Summary & Architectural Philosophy

**SIRIX** (inspired by *Sirius*, the brightest star in the night sky) is the client-facing, device-adaptive Progressive Web Application (PWA) for the autonomous quantitative swing trading engine. Built on the methodologies of Jim Simons and Dr. Marcos López de Prado, the engine operates under a strict **Zero-Override** paradigm: all trade entries, position sizing, trailing stops, and exits are executed algorithmically via end-of-day (EOD) batch pipelines.

Consequently, the SIRIX user interface is designed as an **Institutional Read-Only Telemetry & Risk Control Terminal** governed by three core principles:
1. **Progressive Disclosure:** Surface-level views remain ultra-clean and scannable in under two seconds (displaying macro portfolio health and minimalist equity rows), while deep quantitative telemetry (7-day OHLC candlesticks, `Triple-Barrier` levels, `ATR`, and `Conviction` scores) is revealed on demand via modal/bottom-sheet inspectors or split-pane views.
2. **Semantic Precision & Zero Translation Drift:** Canonical quantitative and financial terms remain locked in English across all supported locales (`EN`, `HE`, `AR`, `RU`), supported by localized interactive `ⓘ` info tooltips.
3. **Curated Multi-Theme Ergonomics:** Users can switch seamlessly between three contrast-calibrated color palettes (`Obsidian Dark`, `Sirius Ice Light`, and `Midnight Sapphire`) via CSS custom properties (`data-theme`) without compromising the semantic legibility of risk and profit indicators.

---

## 2. Modular Documentation Map (`docs/ui-spec/`)

This specification serves as the architectural hub for the SIRIX frontend. Implementation details are divided into four focused modules:

| Module File | Scope & Responsibilities |
| :--- | :--- |
| **`00_SIRIX_MASTER_ARCHITECTURE.md`** *(This File)* | Brand identity, curated theme palettes & CSS tokens, typography, i18n/Bidi rules, canonical term lock, and PWA shell configuration. |
| **`01_PORTFOLIO_HOME_AND_INSPECTOR.md`** | 3-tier Home screen hierarchy, persistent `Portfolio Heat` gauge, `Audit Log` divider bar, minimalist equity list with 14-day `Timeline Bar`, and Deep-Dive Candlestick Inspector. |
| **`02_SEARCH_AUDIT_AND_PREFERENCES.md`** | 3-icon fixed bottom navigation bar, Algorithmic Transparency Search (rejected ticker explanations), closed-trade `Audit Log` view, and User Preferences drawer/view. |
| **`03_DATA_CONTRACTS_AUTH_AND_TIERS.md`** | FastAPI JSON payload contracts, `JWT` session lifecycle, multi-tenant `user_id` isolation, `FREE` / `PRO` / `EXPERT` tier feature-gating, and offline/empty edge states. |

---

## 3. Curated Color Palettes & Design Tokens

All styling MUST be implemented using semantic CSS custom properties bound to `[data-theme="<theme_id>"]` on the root `<html>` element. Hardcoded hex values in component classes are strictly prohibited.

### 3.1 Theme 1: `obsidian-dark` (Default Institutional Dark)
Designed for low-glare nocturnal telemetry and prolonged quantitative monitoring.
* `--bg-canvas`: `#090D16` (Deep Obsidian Slate)
* `--bg-surface`: `#111827` (Elevated Card / Row Container)
* `--bg-surface-hover`: `#1A2234` (Interactive Hover / Active Tap State)
* `--bg-overlay`: `rgba(9, 13, 22, 0.82)` (Modal / Bottom-Sheet Backdrop with `backdrop-blur-md`)
* `--border-subtle`: `#1F2937` (1px Hairline Divider)
* `--border-strong`: `#374151` (Focused Input / Active Card Outline)
* `--text-primary`: `#F9FAFB` (Primary Equity & Ticker Figures)
* `--text-secondary`: `#9CA3AF` (Secondary Labels & Subtitles)
* `--text-muted`: `#6B7280` (Timestamps & Inactive Icons)
* `--accent-brand`: `#06B6D4` (Electric Cyan — Brand Highlight & Active Navigation)

### 3.2 Theme 2: `sirius-ice-light` (Daylight Sky & Ice Blue)
Inspired by Sirius's blue-white luminosity; engineered for high outdoor/daylight legibility using soft sky-blue surfaces rather than harsh pure white.
* `--bg-canvas`: `#F0F7FF` (Soft Glacial Sky Mist)
* `--bg-surface`: `#FFFFFF` (Crisp Pure White Card with subtle elevation shadow `0 1px 3px rgba(14, 116, 144, 0.08)`)
* `--bg-surface-hover`: `#E0F2FE` (Pale Ice Blue Hover State)
* `--bg-overlay`: `rgba(15, 23, 42, 0.45)` (Translucent Slate Backdrop)
* `--border-subtle`: `#BAE6FD` (1px Sky-Blue Hairline Divider)
* `--border-strong`: `#7DD3FC` (Focused Container Border)
* `--text-primary`: `#0F172A` (Deep Navy Ink)
* `--text-secondary`: `#334155` (Slate Navy Secondary Text)
* `--text-muted`: `#64748B` (Muted Blue-Grey Metadata)
* `--accent-brand`: `#0284C7` (Deep Cerulean Blue — High-Contrast Brand Accent)

### 3.3 Theme 3: `midnight-sapphire` (Royal Banking Navy)
An institutional deep-blue alternative for users who prefer a classic quantitative terminal aesthetic over pure black.
* `--bg-canvas`: `#0B192C` (Deep Midnight Sapphire)
* `--bg-surface`: `#132743` (Elevated Royal Navy Surface)
* `--bg-surface-hover`: `#1B365D` (Interactive Navy Highlight)
* `--bg-overlay`: `rgba(7, 16, 30, 0.82)` (Sapphire Backdrop)
* `--border-subtle`: `#1E3A5F` (1px Muted Cobalt Border)
* `--border-strong`: `#2E5488` (Active Border)
* `--text-primary`: `#F1F5F9` (Ice White Primary Text)
* `--text-secondary`: `#94A3B8` (Cool Silver-Blue Secondary Text)
* `--text-muted`: `#64748B` (Muted Cobalt Metadata)
* `--accent-brand`: `#38BDF8` (Luminous Sky Cyan)

### 3.4 Semantic Risk & Profit Tokens (Contrast-Calibrated per Theme)
Profit, stop-loss, and time-decay colors are strictly reserved for quantitative telemetry and calibrated to meet WCAG AA contrast standards across all three palettes:

| Semantic Token | Purpose | Dark / Sapphire Value | `sirius-ice-light` Value |
| :--- | :--- | :--- | :--- |
| `--status-profit` | Positive P&L, `Take-Profit` proximity, Healthy EOD sync | `#10B981` (Emerald) | `#059669` (Deep Emerald) |
| `--status-profit-bg` | Subtle badge tint for positive returns | `rgba(16, 185, 129, 0.14)` | `rgba(5, 150, 105, 0.12)` |
| `--status-risk` | Negative P&L, `Chandelier Stop` proximity, Days 12–14 `Time Barrier` alert | `#EF4444` (Crimson) | `#DC2626` (High-Contrast Red) |
| `--status-risk-bg` | Subtle badge tint for losses or critical stop warnings | `rgba(239, 68, 68, 0.14)` | `rgba(220, 38, 38, 0.10)` |
| `--status-warn` | Days 8–11 `Time Barrier` maturation, `Earnings Blackout` approach | `#F59E0B` (Amber) | `#D97706` (Rich Ochre) |
| `--status-warn-bg` | Subtle badge tint for caution states | `rgba(245, 158, 11, 0.14)` | `rgba(217, 119, 6, 0.12)` |
| `--status-fresh` | Days 1–7 `Time Barrier` progress bar, `Conviction` score | `#06B6D4` (Cyan) | `#0284C7` (Cerulean) |

---

## 4. Typography & Numerical Alignment Rules

1. **Font Families:**
   * **UI & Prose (`--font-sans`):** `'Inter', 'Heebo', 'Noto Sans Arabic', system-ui, -apple-system, sans-serif` (supports Latin, Hebrew, Arabic, and Cyrillic glyphs with unified x-height).
   * **Financial & Quantitative Data (`--font-mono`):** `'JetBrains Mono', ui-monospace, SFMono-Regular, monospace`.
2. **Tabular Numerals Mandate:**
   * Every price (`$53.90`), percentage (`+11.83%`), share count, `ATR` value, and countdown (`Day 6/14`) **MUST** apply `font-family: var(--font-mono)` and `font-variant-numeric: tabular-nums`. This guarantees strict vertical column alignment and zero horizontal jitter during live updates.
3. **Type Scale:**
   * **Hero Portfolio Equity:** `2rem` (`32px`) Mobile / `2.5rem` (`40px`) Desktop, Weight `700`, tight letter-spacing (`-0.02em`).
   * **Section & Screen Headers:** `1.125rem` (`18px`), Weight `600`.
   * **Equity Row Primary (Ticker & Position Value):** `0.9375rem` (`15px`), Weight `600`.
   * **Equity Row Secondary (Share Price & Index Tag):** `0.8125rem` (`13px`), Weight `400`.
   * **Micro Telemetry & Badges:** `0.6875rem` (`11px`), Weight `600`, uppercase tracking (`0.04em`).

---

## 5. Multi-Language (`i18n`), Bidirectional (`RTL`/`LTR`) & Canonical Term Lock

SIRIX supports four interface languages selectable inside **User Preferences**:
* **English (`en`)** — `dir="ltr"`
* **Hebrew (`he`)** — `dir="rtl"`
* **Arabic (`ar`)** — `dir="rtl"`
* **Russian (`ru`)** — `dir="ltr"`

### 5.1 CSS Logical Properties Mandate
To ensure seamless layout mirroring between `LTR` (`en`, `ru`) and `RTL` (`he`, `ar`), physical directional utilities (`ml-*`, `mr-*`, `pl-*`, `pr-*`, `left-*`, `right-*`, `text-left`, `text-right`) are **strictly forbidden**. Developers must use CSS Logical Properties exclusively:
* Spacing: `ms-*` (`margin-inline-start`), `me-*` (`margin-inline-end`), `ps-*`, `pe-*`.
* Positioning: `start-0`, `end-0`.
* Alignment: `text-start`, `text-end`.
* Directional Icons: Chevrons and navigation arrows must mirror automatically in `[dir="rtl"]` using `rtl:rotate-180`, whereas candlestick charts, timeline progress bars (left-to-right time progression), and numerical gauges remain strictly left-to-right.

### 5.2 Bidirectional Isolation (`Bidi`) for Numbers & Tickers
In `RTL` locales (`he`, `ar`), negative signs and currency prefixes can invert visually if unisolated. All ticker symbols, currency values, and signed percentages must be wrapped in an isolated LTR span:
```html
<span dir="ltr" class="font-mono tabular-nums inline-block">-$1,420.50 (-1.43%)</span>
```

### 5.3 Canonical Domain Term Lock (No Translation Rule)
To preserve exact institutional context and prevent semantic loss across languages, **core quantitative and investment terms MUST remain in English** regardless of the active UI language. Surrounding labels, explanations, and interactive tooltips are translated into the user's selected language.

**Locked Canonical English Terms:**
* `Triple-Barrier`
* `Chandelier Stop`
* `Take-Profit`
* `Time Barrier`
* `Portfolio Heat`
* `Conviction`
* `ATR`
* `Zero-Override`
* `Earnings Blackout`
* `Audit Log`
* `RUT` / `MID` (Index identifiers)

### 5.4 Localized Hybrid Info Tooltips (`ⓘ`)
Every locked canonical term displayed in the UI is paired with a subtle `ⓘ` trigger icon:
* **Desktop (`>= 1024px`):** Opens an accessible popover on hover or focus, displaying the localized plain-language explanation and rule threshold (e.g., explaining in Hebrew/Arabic/Russian how `Chandelier Stop` ratchets upward using $3 \times \text{ATR}$ and never moves down).
* **Mobile (`< 1024px`):** Opens on tap and dismisses cleanly on outside tap or explicit close button, avoiding sticky mobile hover states.

---

## 6. Adaptive Layout Breakpoints & PWA Configuration

### 6.1 Responsive Breakpoints
* **Mobile PWA (`< 768px` — Primary Target: iOS Safari / Android Chrome):**
  * Single-column viewport (`100dvh` safe-area aware, respecting `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)`).
  * Fixed 3-icon Bottom Navigation Bar (`56px` height + bottom safe area).
  * Deep-Dive Position Inspector renders as a slide-up **Bottom Sheet** (`85dvh` max height) preserving the underlying list scroll position.
* **Tablet & Desktop (`>= 1024px` — Chromebook / Desktop Web):**
  * Centered or **Master-Detail Split View** (`max-w-6xl` container): Left pane (`420px` fixed width) houses the Portfolio Summary, `Audit Log` trigger, and scrollable Equity List; Right pane (`flex-1`) renders the live **Deep-Dive Candlestick & Triple-Barrier Inspector** for the currently selected ticker (eliminating modal open/close friction on wide screens).

### 6.2 Progressive Web App (`manifest.json`) Standards
* **Display Mode:** `standalone` (hides browser URL chrome for native app feel).
* **App Name / Short Name:** `SIRIX`
* **Dynamic Theme Color:** `<meta name="theme-color">` updates dynamically via JavaScript whenever the user switches between `obsidian-dark` (`#090D16`), `sirius-ice-light` (`#F0F7FF`), and `midnight-sapphire` (`#0B192C`) so the iOS/Android status bar blends seamlessly with the canvas.
* **Offline Resilience:** Service Worker implements a `Stale-While-Revalidate` strategy for API telemetry responses, displaying a subtle `Offline Snapshot` badge with the last EOD sync timestamp when network connectivity is unavailable.