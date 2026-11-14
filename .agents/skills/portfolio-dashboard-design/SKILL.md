---
name: portfolio-dashboard-design
description: >-
  Design system, layout architecture, CSS component conventions, mobile RWD rules,
  Chromium Liquid Glass performance pitfalls, and build workflow for
  code/portfolio_dashboard. Activate BEFORE modifying or adding any UI, tab,
  chart, table, filter, or theme feature in code/portfolio_dashboard/builder.py
  or tracker.py.
---

# Portfolio Dashboard Design & Engineering Skill

This skill governs all UI, visual design, layout, and frontend engineering work in `code/portfolio_dashboard/` (`builder.py`, `tracker.py`, and `dist/index.html`). Follow every rule below so new tabs, cards, charts, and controls look cohesive with the existing macOS Liquid Glass + Fugle financial dashboard and avoid regressions.

---

## 1. Visual Identity & Design Tokens

- **Aesthetic**: Apple macOS / iOS **Liquid Glass** (cool slate-blue / glacier-silver, **no** purple/rainbow neon clutter) paired with **Fugle-style high-density financial tables**.
- **Themes (3-way toggle)**:
  - `theme-light` is the **default** (`<meta name="theme-color" content="#dce5f0">`).
  - `theme-dark` uses deep slate (`<meta name="theme-color" content="#060b14">`).
  - `auto` follows `prefers-color-scheme`.
  - Always use CSS variables (`--text-main`, `--text-muted`, `--text-dim`, `--glass-bg`, `--glass-border`, `--primary-accent`, `--table-hover`, `--well-bg`, etc.) — **never** hardcode hex colors that break light or dark mode.
- **Taiwan Stock Color Convention**:
  - **Up / Gain / Buy** = Red (`--color-up`, `.badge-pnl.up`).
  - **Down / Loss / Sell** = Green (`--color-down`, `.badge-pnl.down`).
- **Typography**:
  - UI text: `var(--font-sans)` (`Plus Jakarta Sans`, `Noto Sans TC`).
  - Numbers, prices, dates, ticker codes: `var(--font-mono)` (`JetBrains Mono`).

---

## 2. File Structure & Critical `builder.py` Syntax Rule

- `code/portfolio_dashboard/tracker.py`: Aggregates account state, FIFO buy-lots, market quotes, backend reports, trade history, competition ranks, friction costs, and LiteLLM usage into `summary_data`.
- `code/portfolio_dashboard/builder.py`: Generates a single self-contained `code/portfolio_dashboard/dist/index.html` using a Python `f"""..."""` template.
  - **CRITICAL**: Inside the HTML/CSS/JS template in `builder.py`, every literal `{` and `}` MUST be doubled as `{{` and `}}`. JavaScript template interpolations must be written as `${{expr}}`.
- **Build & Verify Command**:
  Always rebuild using the project Conda environment (default system `python` lacks `esun_marketdata`):
  ```powershell
  C:\Users\CodyLiao\miniconda3\envs\esunaicup2026_py311\python.exe "h:\我的雲端硬碟\DataScience\2026玉山人工智慧賽\code\portfolio_dashboard\builder.py" --offline
  ```

---

## 3. Standard Component Reuse (Do Not Improvise Raw Controls)

When adding a new feature or tab, **reuse the existing CSS classes** verbatim instead of inventing inline styles or borrowing classes from unrelated controls:

### A. Cards & KPI Grids
- Wrap sections in `<div class="glass-card">`.
- Top summary metrics use `<div class="kpi-grid">` containing `<div class="glass-card kpi-card">` with `.kpi-label`, `.kpi-value`, and `.kpi-subtext`.
- Prefer **even** KPI card counts (4 or 6) so desktop (`auto-fit, minmax(200px, 1fr)`) and mobile (2-column grid) stay balanced without orphan cards.

### B. Tables & Toolbars
- Standard structure:
  ```html
  <div class="glass-card">
    <div class="table-toolbar">
      <div>
        <div class="chart-title"><span>🧾</span> Section Title</div>
        <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">Subtitle</div>
      </div>
      <!-- right-side controls -->
    </div>
    <div class="table-container">
      <table class="fugle-table">
        <thead>...</thead>
        <tbody>...</tbody>
      </table>
    </div>
  </div>
  ```
- **Non-sortable headers**: `table.fugle-table th` has `cursor: pointer` and hover highlights by default. If a table does **not** support column sorting, add `class="no-sort"` to its `<th>` elements so hovering doesn't flash a misleading highlight band.
- **Column alignment**: `th` and `td` default to `text-align: right` except columns 1 and 2 (`left`). If column 3+ contains `.stock-tag-box` or text labels, explicitly set `style="text-align: left;"` on that `<th>` and `<td>`.

### C. Dropdowns (`<select>`)
- **ALWAYS** use `class="report-select"` for `<select>` controls.
- **NEVER** put `.search-input` on a `<select>` (`.search-input` reserves `padding-left: 38px` for `.search-icon` and lacks custom chevron & dark/light `<option>` styling).

### D. Search Inputs
- Always wrap `<input class="search-input">` inside `<div class="search-box">` with `<span class="search-icon">🔍</span>`.
- Always put `align-items: center;` on the flex container holding `.search-box` alongside `.filter-pills` or `.report-select`; otherwise `.search-box` stretches vertically and misaligns both the input and the `🔍` icon.

### E. Filter Pills & Badges
- Use `.filter-pills` + `.filter-btn` (`.active`) for segmented filter toggles.
- Use `.badge-pnl.up` / `.badge-pnl.down` for gains/losses or buy/sell tags.
- Use `.model-badge.flash` / `.model-badge.argon` and `.code-exec-badge` in AI model routing views.

### F. Chart.js Instances
- Whenever adding a new Chart.js chart, register its global reference in `updateChartTheme()` so switching between Light / Dark / Auto immediately updates grid lines, tick colors, and legend text colors.
- For integer-only axes (e.g., competition rank), set `ticks: {{ precision: 0 }}`.

---

## 4. Tab Navigation & Mobile RWD Rules

- **Current Tab Order (6 tabs)**:
  1. `📊 帳戶總覽` (`tab1`)
  2. `📈 行情群組` (`tab2`)
  3. `🧾 歷史成交明細` (`tab6`)
  4. `📄 決策報告` (`tab4`)
  5. `🤖 AI 模型成本監控` (`tab3`)
  6. `💡 專案亮點` (`tab5`)
- Keep tab labels concise (2–8 chars) so `.sticky-top-dock.is-scrolled` stays on a single horizontal row on desktop.
- **Mobile 2-column Grid (`@media (max-width: 768px)`)**:
  - `.segmented-control` uses `grid-template-columns: repeat(2, minmax(0, 1fr))`.
  - With an **even** number of tabs (currently 6), **never** set `grid-column: 1 / -1` on any tab button. (Only use `grid-column: 1 / -1` on the last tab if the total tab count becomes odd.)
- **Prevent Mobile Horizontal Overflow**:
  - Native `<select>` elements expand to their longest `<option>` text unless constrained. `.report-select`, `.report-controls-left`, `.report-controls-right`, and `.report-meta-pill` must keep `max-width: 100%; min-width: 0; overflow: hidden; text-overflow: ellipsis;`.
  - On `<= 768px`, full-width date/file selectors (like `#reportDateSelect`) should span `width: 100%; flex: 1 1 100%; order: -1;` above prev/next buttons.

---

## 5. Chromium `backdrop-filter` & Compositor Pitfalls

- **Avoid adjacent/nested `backdrop-filter` repaints**:
  - `.segmented-control` must **NOT** have `backdrop-filter` (the outer `.sticky-top-dock.is-scrolled` already provides blur when floating).
  - `.sticky-top-dock` keeps `transform: translateZ(0);` and `.glass-card` keeps `isolation: isolate;`.
  - Without this isolation, hovering `.tab-btn` above tall `.glass-card` containers (such as long tables or long Markdown reports) causes Chromium's GPU compositor to flash a horizontal shadow/seam across the card below.
- **Never use `transition: all`** on `.tab-btn` or glass buttons; explicitly transition only `background`, `color`, `border-color`, `box-shadow`, and `transform`.

---

## 6. Privacy & Competition Security Boundary

- In public/showcase tabs (e.g., Tab 5 `💡 專案亮點`), present **architectural and engineering highlights only** (pipeline structure, Code Execution, LiteLLM routing, schema validation, FIFO tracking, deployment).
- **Never** expose proprietary prompt wording, candidate pool stock lists/counts, or internal risk-control thresholds.

---

## 7. Pre-Completion Verification Checklist

Before finishing any dashboard edit:
1. Run `builder.py --offline` with the `esunaicup2026_py311` Python interpreter and verify Exit Code `0`.
2. Confirm all `{` / `}` in newly added CSS/JS are properly escaped as `{{` / `}}`.
3. Verify both **Light** and **Dark** theme CSS variables are respected.
4. Verify mobile (`<= 768px`) RWD: no `<select>`, table toolbar, or tab grid causes horizontal overflow.
5. If modifying AI pipeline metadata (e.g. model routing, fallbacks, Code Execution stages), cross-check `code/models_config.yaml` and the agent scripts before writing UI copy.
