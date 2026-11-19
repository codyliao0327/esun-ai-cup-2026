---
name: portfolio-dashboard-design
description: >-
  Complete design philosophy, visual system, exact CSS component catalog,
  information design rules, mobile RWD layout constraints, Chromium GPU/scroll
  performance engineering, and build workflow for code/portfolio_dashboard.
  MUST read and follow BEFORE modifying or adding any UI, tab, subview, chart,
  table, filter, or theme feature in code/portfolio_dashboard/builder.py or
  tracker.py.
---

# Portfolio Dashboard Design & Engineering Skill

This skill is the authoritative specification for `code/portfolio_dashboard/` (`builder.py`, `tracker.py`, `dist/index.html`). Every new tab, subview, card, chart, table, and interactive control MUST follow these rules so the dashboard stays visually cohesive, data-accurate, mobile-safe, and 60fps-smooth.

---

## 1. Design Philosophy & Visual Language

- **Core Aesthetic**: Apple macOS / iOS **Liquid Glass** (cool slate-blue & glacier-silver palette) combined with **Fugle-style high-density financial tables**.
  - **No neon / purple / pink clutter**: Stick to glacial sky blue (`--primary-accent`: `#0284c7` light / `#38bdf8` dark) and clean translucent glass surfaces.
  - **Clean rounded geometry**: Cards use `border-radius: 26px` with uniform subtle borders (`--glass-border` or soft tinted accent border). **NEVER** add thick `border-left: 4px solid ...` accent stripes on rounded `.glass-card` elements — it slices awkwardly across the rounded corners and breaks the Liquid Glass feel.
- **Theme System (2-Mode Cyclic Toggle, Default Light)**:
  - `theme-light` is the **default** (`--bg-solid: #dce5f0`, `<meta name="theme-color" content="#dce5f0">`).
  - `theme-dark` is the dark theme (`--bg-solid: #060b14`, `<meta name="theme-color" content="#060b14">`).
  - Header theme control is a **single icon-only circular button** (`#themeToggleBtn`, `.theme-cycle-btn`): shows `🌙` when light, `☀️` when dark, toggles between light/dark only (no text labels, no `auto`/system mode, and hidden automatically inside `.sticky-top-dock.is-scrolled`).
  - **Theme-aware styling**: Always use CSS variables (`--text-main`, `--text-muted`, `--text-dim`, `--glass-bg`, `--glass-border`, `--primary-accent`, `--table-hover`, `--well-bg`, etc.). Whenever you add a custom tinted highlight (e.g., `tr.ranking-my-team-row`, `.group-badge.society`, `.ranking-my-team-banner`), you **MUST** define both the dark default AND an `html.theme-light ...` rule so contrast looks sharp in both themes.
- **Taiwan Stock Market Color Convention**:
  - **Up / Gain / Buy** = Red (`--color-up`, `.badge-pnl.up`).
  - **Down / Loss / Sell** = Green (`--color-down`, `.badge-pnl.down`).
- **Typography**:
  - UI text: `var(--font-sans)` (`Plus Jakarta Sans`, `Noto Sans TC`).
  - All numbers, prices, percentages, dates, ranks, and ticker codes: `var(--font-mono)` (`JetBrains Mono`).

---

## 2. Exact CSS Component Catalog (Zero Improvisation Rule)

**CRITICAL**: Before writing any HTML in `builder.py`, verify that every CSS class you reference actually exists in `builder.py`. Do **NOT** invent fake class names (like `.theme-btn`, which does NOT exist and falls back to an ugly unstyled browser button!) and do **NOT** misuse a class meant for a different control.

| UI Element | Required Class / Markup | Common Mistake to AVOID |
| :--- | :--- | :--- |
| **Standalone Action / Back / CTA Button** | `<button type="button" class="report-action-btn">` | NEVER use `.theme-btn` (doesn't exist) or `.filter-btn` outside `.filter-pills`. |
| **Segmented Filter Group** | `<div class="filter-pills"><button class="filter-btn [active]">...</button></div>` | Do not place standalone `.filter-btn` outside `.filter-pills`. |
| **Dropdown (`<select>`)** | `<select class="report-select">` | NEVER put `.search-input` on `<select>` (wrong left padding, no chevron, broken `<option>` theme colors). |
| **Search Input** | `<div class="search-box"><span class="search-icon">🔍</span><input class="search-input"></div>` | Parent flex row MUST have `align-items: center;`, otherwise `.search-box` stretches vertically and misaligns the `🔍` icon. |
| **Timestamp / Metadata Pill** | `<span class="report-meta-pill">行情更新於 ...</span>` | Keep concise; do not duplicate global header info (like Day X/Y) unnecessarily. |
| **Card Container** | `<div class="glass-card">` | Do not add `border-left: 4px solid ...` or inline `backdrop-filter` overrides. |
| **KPI Summary Row** | `<div class="kpi-grid">` with `<div class="glass-card kpi-card">` (`.kpi-label`, `.kpi-value`, `.kpi-subtext`) | Prefer even counts (4 or 6) so 2-column mobile grids have no orphan card. |
| **Data Table** | `.glass-card` → `.table-toolbar` → `.table-container` → `<table class="fugle-table">` | Add `class="no-sort"` on `<th>` if the table is NOT sortable (prevents misleading hover highlight & pointer cursor). |
| **Table Column Alignment** | Default: col 1 & 2 are `left`, col 3+ are `right` (numbers). | If col 3+ contains text, badges, or `.stock-tag-box`, explicitly set `style="text-align: left;"` on BOTH `<th>` and `<td>`. |
| **PnL / Side / Model Badges** | `.badge-pnl.up` / `.badge-pnl.down`, `.model-badge.flash` / `.model-badge.argon`, `.code-exec-badge` | Never apply `.badge-pnl.down` to `null`/`undefined` values (render neutral `--` instead). |

---

## 3. Information Design & Data Integrity Rules

When building new views (such as leaderboards, analytics, or subviews), enforce strict data clarity:

1. **Every KPI card must tell ONE coherent story**:
   - Title, primary value, and subtext must belong to the same metric/entity. Never stuff unrelated stats into a card's subtext (e.g., never put "全體 #1" inside a "學生組隊伍數" card).
2. **Distinguish asynchronous data timestamps clearly**:
   - Market quotes (`market_cache.json` → `updated_at`) update right after market close, while DataPack account snapshots (`summary_data["as_of_date"]`) update later in the evening.
   - Show `行情更新於 YYYY-MM-DD HH:MM` (and `帳戶基準日 YYYY-MM-DD` on holdings) so users always know whether prices or holdings are newer.
3. **Never hardcode dynamic counts or schedules**:
   - Competition progress (`賽期 X/Y 天`) is computed dynamically via `compute_competition_progress()` matching `code/L0_sources/datapack_loader.py` (`COMPETITION_START_DATE = "2026-10-27"`, `COMPETITION_END_DATE = "2026-11-27"`).
   - Watchlist (`觀察標的`) is parsed dynamically from `STOCK_IDS` in `code/L0_sources/finlab_market_loader.py` via `ast.parse` (zero heavy imports, count computed at build time).
4. **Null-safe formatting & sorting**:
   - Check `val !== null && val !== undefined && !isNaN(val)` before rendering colored `.badge-pnl` tags; render neutral `<span style="color:var(--text-dim);">--</span>` for missing values.
   - When sorting columns with nullable values (e.g., `rank_diff`, `prev_rank`), explicitly push `null` rows to the bottom (`return 1` / `-1`) regardless of ascending or descending direction — **never** use sentinel numbers like `-999999` (which jump to the top when sorted ascending!).
5. **Context-aware metrics**:
   - If the dataset provides group-level fields (e.g., `prev_group_rank` vs `prev_rank`), switch the column calculation and header label dynamically when the user filters by group (`組名次變動` vs `總名次變動`).
6. **Chart.js Theme Sync & Axes**:
   - Register every new Chart.js instance in `updateChartTheme()` so Light ⇄ Dark toggling updates grid lines, tick labels, and legends live.
   - Set `ticks: {{ precision: 0 }}` on integer axes (e.g., ranks).

---

## 4. Navigation, Layout & Mobile RWD Rules

- **Header (`#dateBadge`)**: Displays `基準日: YYYY-MM-DD · 賽期 X/Y 天`.
- **Current 6 Tabs (Fixed Order & Concise Names)**:
  1. `📊 帳戶總覽` (`tab1`, includes embedded `#tab1RankingView` subview; clicking `tab1` resets to overview via `closeRankingView(false)`)
  2. `📈 行情群組` (`tab2`, 4 filter groups: `我的持股` / `觀察標的` / `其餘標的` / `全部`)
  3. `🧾 歷史成交明細` (`tab6`)
  4. `📄 決策報告` (`tab4`, sticky TOC + scrollspy)
  5. `🤖 AI 模型成本監控` (`tab3`, routing pills MUST match `code/models_config.yaml`)
  6. `💡 專案亮點` (`tab5`)
- **Mobile 2-Column Tab Grid (`@media (max-width: 768px)`)**:
  - `.segmented-control` uses `grid-template-columns: repeat(2, minmax(0, 1fr))`.
  - With an **even** number of tabs (currently 6), **never** apply `grid-column: 1 / -1` to any tab button.
- **Prevent Mobile Horizontal Overflow**:
  - Native `<select>` expands to its longest `<option>` unless constrained. Keep `max-width: 100%; min-width: 0; overflow: hidden; text-overflow: ellipsis;` on `.report-select`, `.report-controls-left`, `.report-controls-right`, and `.report-meta-pill`.
  - On `<= 768px`, stack toolbar controls cleanly (`width: 100%`, `.search-box { flex: 1 1 100%; min-width: 0; }`, `#reportDateSelect { width: 100%; flex: 1 1 100%; order: -1; }`).

---

## 5. Chromium GPU, Sticky & Scroll Performance Rules

These rules were battle-tested to eliminate **fast-scroll white flashes**, **sticky traps**, and **hover shadow seams** in Chromium on Windows & mobile:

1. **Background & Anti-White-Flash Architecture**:
   - `html` and `body` MUST keep `background-color: var(--bg-solid, #dce5f0);` so overscroll or fast-scroll tile rasterization never flashes pure white.
   - Multi-layer gradients (`var(--ambient-orb-1), var(--bg-gradient)`) live inside the single viewport-sized fixed layer `.ambient-glow` (`position: fixed; inset: 0; transform: translateZ(0);`) — rasterized once, zero scroll repaint cost.
2. **Selective `backdrop-filter` Budget**:
   - **KEEP `backdrop-filter: var(--glass-backdrop)` ONLY** on compact floating overlays where content actively scrolls behind them: `.sticky-top-dock.is-scrolled` and `.report-toc-card`.
   - **DO NOT put `backdrop-filter`** on `.glass-card` (especially tall tables/reports) or `.segmented-control`: blurring 3000px+ cards over a smooth gradient is visually redundant, exhausts GPU offscreen texture budgets (causing white flashes during fast scroll), and triggers Chromium hover seam artifacts.
   - Keep `.sticky-top-dock` with `transform: translateZ(0);`, `.glass-card` with `isolation: isolate;`, `.table-container` with `contain: layout style;`, and `table.fugle-table tbody tr` with `content-visibility: auto; contain-intrinsic-size: auto 52px;`.
3. **Never Break `position: sticky`**:
   - `html` and `body` MUST use `overflow-x: clip;` — **NEVER** `overflow-x: hidden;` (which creates a scroll container that disables `position: sticky` on `.report-toc-card`).
4. **Scrollspy Must NEVER Call `scrollIntoView()`**:
   - Calling `btn.scrollIntoView()` inside a `window` scroll handler scrolls ancestor containers including `window`, locking/yanking the page back up whenever the TOC is static (`<= 960px`) or near viewport edges.
   - Instead, track `_lastActiveReportTocIdx`, skip redundant DOM updates, and adjust `tocCard.scrollTop` directly **only** when `getComputedStyle(tocCard).position === 'sticky'`.
5. **No `transition: all`**:
   - Never use `transition: all` on `.tab-btn` or interactive buttons; list explicit properties (`background`, `color`, `border-color`, `box-shadow`, `transform`).

---

## 6. Build Workflow, Template Syntax & Privacy Boundary

- **Python `f"""..."""` Escaping in `builder.py`**:
  - Every literal `{` and `}` in HTML/CSS/JS inside `builder.py` MUST be escaped as `{{` and `}}`. JS template literals MUST be `${{expr}}`.
- **Mandatory Build Command** (default system `python` lacks `esun_marketdata`):
  ```powershell
  C:\Users\CodyLiao\miniconda3\envs\esunaicup2026_py311\python.exe "h:\我的雲端硬碟\DataScience\2026玉山人工智慧賽\code\portfolio_dashboard\builder.py" --offline
  ```
- **Competition Privacy Boundary**:
  - Public showcase tabs (e.g., Tab 5 `💡 專案亮點`) describe high-level engineering architecture only — **never** expose proprietary prompt wording, candidate pool stock lists/counts, or internal risk thresholds.

---

## 7. Pre-Completion Verification Checklist

Before declaring any dashboard change complete:
1. Run `builder.py --offline` with `esunaicup2026_py311\python.exe` and verify **Exit Code 0**.
2. Audit every newly added HTML class name against the CSS in `builder.py` (zero undefined classes!).
3. Verify both **Light** (default) and **Dark** theme contrast for every new card, badge, and chart.
4. Check mobile (`<= 768px`) RWD: no `<select>`, `.search-box`, toolbar, or tab grid overflows horizontally.
5. Check scroll behavior: no `overflow-x: hidden` on `html`/`body`, no `scrollIntoView()` in scroll handlers, no `backdrop-filter` added to `.glass-card`.
6. Cross-check any AI pipeline / model routing UI copy against `code/models_config.yaml` and actual agent scripts.
