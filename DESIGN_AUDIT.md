# DESIGN_AUDIT.md

Phase 0 — audit only. **No code was changed.**

Scope audited: `templates/` (53 files), `static/css/`, `static/js/`, `landing/`,
`rentritz-landing/`. Excluded: `node_modules/`, `venv/`, `.claude/worktrees/`
(a stale copy of the tree, not the working source).

---

## ✅ SCOPE REVISION — decisions taken, counts restated

The original brief is **void**. Decision: **consolidate the existing design**;
invent no new colours, fonts, shadows, or radii. **Reference page:
`templates/core/landing.html`** — every token collision resolves to its current
value.

### Permanent exclusions

| Excluded | Files | Hex removed from scope | Reason |
|---|---|---|---|
| Transactional email | 7 templates (6 carry hex) | **94** | Email clients do not support CSS custom properties. Inline hex is **correct** here, not a violation. |
| Dark admin panel | 18 templates + `static/css/admin.css` | **46** | **Named permanent exception to light-mode-only.** The admin surface stays dark and stays on Inter. |

### Corrected counts (in scope only)

| Metric | Original audit | **In scope after revision** |
|---|---|---|
| Pages | 34 user-facing | **26** (9 public + 4 auth + 7 lawyer + 6 error) |
| Raw hex occurrences | 607 | **398** |
| Files containing hex | 36 | **21** |
| Distinct `:root` systems to merge | 3 | **2** (`main.css` + `landing.html`; admin is exempt) |
| Font loads to collapse | 8 | **6 in scope** (admin's Inter load is exempt) |

Out of scope but not excluded — pending the deletion decision below: `rentritz-landing/index.html` (58 hex), `landing/App.jsx` (9), `static/manifest.json` (2). These 69 make up the difference between 398 and 467.

### ⚠️ Accepted trade-off — landing is no longer self-contained

Extracting landing's `:root` into `static/css/tokens.css` **removed the landing
page's self-containment**. Before, `templates/core/landing.html` carried its own
tokens inline and rendered correctly from any context, including opening the file
straight off disk. Now it depends on an external stylesheet.

**Failure mode:** if `tokens.css` fails to load in production, landing does not
degrade gracefully — every `var()` reference becomes invalid, colour declarations
are dropped, and text falls back to initial black. Over the dark photographic
hero that means **dark-on-dark and unreadable**, not merely unstyled.

**This was accepted deliberately**, to avoid two token systems drifting apart —
the exact duplication this refactor exists to remove. Recorded here so nobody is
surprised later.

**Known benign trigger:** opening `templates/core/landing.html` directly from
disk (`file://`) always reproduces the unreadable state, because
`{{ url_for(...) }}` is Jinja and only resolves when Flask renders the template.
Off disk the `href` stays a literal `{{ ... }}` string, the stylesheet 404s, and
the page looks broken. **Always verify landing through Flask, never via `file://`.**

#### Verification through Flask — 2026-08-12, commit `fda47e1`

| Check | Result |
|---|---|
| `GET /` | **200** |
| `GET /static/css/tokens.css` | **200**, correct content |
| `<link>` before `<style>` in `<head>` | **Yes** — link line 12, `<style>` line 14 |
| `url_for` output | resolves to `/static/css/tokens.css`, served by Flask's static handler |
| Loaded stylesheets (browser) | DM Sans, `http://localhost:5055/static/css/tokens.css`, inline |
| Token resolution (computed) | `--paper #f8f6f2`, `--ink #1c1916`, `--amber #c8820a`, `--amber-soft #e0a040`, `--muted #6b6157`, `--ease cubic-bezier(0.22,1,0.36,1)` — all resolve |
| `body` background (computed) | `rgb(248, 246, 242)` = `--paper` ✅ |
| Hero heading legibility | **Readable** — light heading over the dark hero photo, amber italic accent intact |

**Verdict: landing is not broken.** The dark-on-dark screenshot was a `file://`
testing artifact, exactly as predicted. No revert required; `4280438` stands.

### Contrast — the current amber already fails AA. Crimson is a fix, not a risk.

Operator-supplied, independently recomputed here from the WCAG 2.x relative
luminance formula. Both agree:

| Foreground | Background | Ratio | AA normal text (4.5:1) |
|---|---|---|---|
| `#c8820a` amber | `#f8f6f2` paper | **2.92:1** | **FAILS** — current state |
| `#D6263A` crimson | `#FFFBFA` paper | **4.87:1** | passes |
| `#9B1B2B` brand-deep | `#FFFBFA` paper | **7.90:1** | passes comfortably |

**This reframes F13 entirely.** All 107 `color: var(--amber)` sites are *already*
below the accessibility minimum and have been since the design was written. The
R1 migration does not introduce a contrast risk on those sites — it **removes**
one that already exists. Even the tightest R1 pair clears AA, and routing text to
`--brand-deep` per the F13 property map puts it near 8:1.

Consequence for review: do not treat "crimson text on paper" as the thing to
scrutinise. The thing to scrutinise is any site the property map sends to
`--brand` (a fill token) that is actually rendering text.

### Resolved blockers

- **B1 — resolved.** Consolidate, do not adopt a new system.
- **B2 (amber) — resolved.** `--amber` = **`#c8820a`** (landing's value). Admin retains `#f59e0b` under its exemption.
- **B3 (dark admin) — resolved.** Permanent documented exception, recorded above.
- **B4 (email) — resolved.** Excluded, recorded above.
- **B6 (Playfair) — resolved.** Delete the 16 declarations in `main.css` and declare Georgia explicitly. Do **not** load Playfair. Zero visual change, since Georgia is what already renders.
- **B5 (duplicate landing) — investigated, see below. Nothing deleted yet.**
- **B7 (check script) — resolved.** Phase 3 fails on any hex in `templates/` (excluding `templates/email/`) and any `font-family` outside `static/css/main.css`.

### B5 findings — is `rentritz-landing/` referenced anywhere?

Searched `render_template` calls, `{% extends %}`, `{% include %}`, Flask static
config, and all deploy/config files:

| Check | Result |
|---|---|
| `render_template('core/landing.html')` | **`app/core/routes.py:62`** — the Jinja landing is **LIVE** |
| Any reference to `rentritz-landing` | **None.** The 3 string matches are the npm `"name"` field in `landing/package.json` and its lockfile — a *different* directory that merely shares the name |
| `{% extends %}` / `{% include %}` naming a landing file | **None** |
| Flask `static_folder` | `static/` only — `rentritz-landing/` is **not served** |
| nginx / vercel / netlify / Procfile / Docker / systemd | **No deploy config exists in the repo at all** |

**Conclusion:** `rentritz-landing/index.html` is unreachable in this repository.
`landing/` (React/Vite) is likewise unrouted, and its `dist/` is never served by Flask.

**I have deleted nothing.** Two caveats worth your judgement before I do: deployment
may happen outside the repo (a CI job or server config not committed here), and
`landing/` is a real Vite project someone may still be developing. Confirm and I
will remove `rentritz-landing/` in its own commit.

---

## ⛔ SUPERSEDED — the original brief described a different codebase

*(Retained for the record. Resolved by the scope revision above.)*

The specification given for this task cannot be applied to this repository as
written. This is not a judgement call about a few tokens; the entire named
substrate is absent. Verified by direct search:

| Brief says | Reality in this repo |
|---|---|
| "Scan every file under `src/`" | **No `src/` directory exists** anywhere (excl. `node_modules`) |
| `tailwind.config.js` is the colour source of truth | **Tailwind is not used at all** — not a dependency, not a CDN link, zero utility classes |
| `src/index.css` holds all font imports | **Does not exist** |
| Delete font imports in `src/features/landing/LandingPage.css` | **Does not exist** |
| Easing from `src/lib/uiMotion.js` | **Does not exist** |
| Tokens `chilli` / `crop` / `ember` / `ink` / `coorg` | **Zero occurrences** in the codebase |
| Fonts: Hanken Grotesk, Bricolage Grotesque, Noto Sans Kannada | **Zero occurrences.** Actual fonts are DM Sans, Inter, Playfair Display, Cormorant Garamond |
| "Kannada text via `.kn` class" | No Kannada anywhere. The product is **Rentritz Dubai** |
| Tailwind `gray-*` overridden to ink scale | No Tailwind, so no `gray-*` utilities to count |

The only token name that overlaps is `--paper-2`, defined inline in
[templates/core/landing.html:21](templates/core/landing.html:21) as `#f0ece6`
— which is **not** the brief's `#F4F0EC`.

This is a **Flask + Jinja2** application (server-rendered HTML, hand-written CSS)
with one small standalone React/Vite marketing app in `landing/`. There is no
component framework and no design-token build step of any kind.

**What I did instead:** I ran the audit the brief actually asks for — fonts,
colours, shadows, radii, transitions, and local colour definitions, per page —
against the real code, and I have documented what the *de facto* design system
is. I did **not** invent a token layer, and I did **not** map real colours onto
`chilli`/`crop`/`ember`/`ink`, because the brief explicitly forbids inventing
tokens. **Phases 1–4 cannot start until this is resolved** — see
"Questions for you" at the end.

---

## 1. Pages and top-level routes

Three separate, unrelated design systems are in play. Which one a page gets is
determined entirely by which base template it extends.

### System A — public app (`templates/base.html` → `static/css/main.css`)
Light, warm/cream, brass-amber accent. **DM Sans.**

| Route | Template | Fonts actually resolved | Off-token issues |
|---|---|---|---|
| `/dashboard` | `core/dashboard.html` | DM Sans + **Georgia** (Playfair fallback) | 25 hex, 26 local `font-family`, 2 `<style>` blocks |
| `/consult/<slug>` | `core/wizard.html` | DM Sans + Georgia | 8 hex, 10 local `font-family` |
| `/answer/<id>` | `core/answer.html` | DM Sans + Georgia | 17 hex, 17 local `font-family` |
| `/history` | `core/history.html` | DM Sans + Georgia | 12 hex, 10 local `font-family` |
| `/credits` | `core/credits.html` | DM Sans + Georgia | 15 hex, 22 local `font-family` |
| `/terms` | `core/terms.html` | DM Sans | 13 hex |
| `/privacy` | `core/privacy.html` | DM Sans | 24 hex |
| `/lawyers/` | `lawyers/browse.html` | DM Sans | 16 hex |
| `/lawyers/<id>` | `lawyers/profile.html` | DM Sans | 22 hex |
| `/lawyers/dashboard` | `lawyers/dashboard.html` | DM Sans | 18 hex |
| `/lawyers/edit-profile` | `lawyers/edit_profile.html` | DM Sans | 10 hex |
| `/lawyers/register` | `lawyers/register.html` | DM Sans | 10 hex |
| `/lawyers/login` | `lawyers/login.html` | DM Sans | 4 hex |
| `/lawyers/bookings/<id>/review` | `lawyers/review.html` | DM Sans | 10 hex |
| `/auth/login` | `auth/login.html` | DM Sans | 3 hex |
| `/auth/register` | `auth/register.html` | DM Sans | 2 hex |
| `/auth/reset-password/<token>` | `auth/reset_password.html` | DM Sans | 2 hex |
| `/auth/forgot-password` | `auth/forgot_password.html` | DM Sans | clean |
| error pages 400/401/403/404/429/500 | `errors/*.html` | DM Sans | **clean — 0 hex, 0 local styles** |

### System B — admin (`templates/admin/base_admin.html` → `static/css/admin.css`)
**Dark theme.** `background: #111111`, `color: #ffffff`. **Inter.**

| Route | Template | Off-token issues |
|---|---|---|
| `/admin/login` | `admin/login.html` | standalone (extends nothing), 19 hex |
| `/admin/` | `admin/dashboard.html` | 2 hex |
| `/admin/categories`, `/admin/scenarios`, `/admin/users`, `/admin/questions`, `/admin/payments`, `/admin/lawyers/`, `/admin/specialisations`, + forms, `tree_builder`, `bulk_import`, detail pages | 16 further templates | mostly clean; `lawyer_detail` and `lawyers_list` 1 hex each; `scenario_preview` has 2 local `font-family` |

> **Direct conflict with the brief.** The brief states *"Light mode only. There is
> NO dark mode."* There are no `prefers-color-scheme` blocks anywhere (confirmed:
> zero matches) — but the entire admin surface, 19 templates, is a hard-coded
> dark UI. Converting it to light is a **visual redesign**, not a token swap.
> **I have not touched it.** See "Questions for you".

### System C — standalone marketing pages (extend nothing, fully self-contained)

| Route | File | Fonts | Notes |
|---|---|---|---|
| `/` (landing) | `core/landing.html` | DM Sans only | **2185 lines**, own inline `:root`, 58 hex |
| `/for-lawyers` | `core/for_lawyers.html` | DM Sans | own font `<link>`, 43 hex, 7 local `font-family` |
| — (not routed) | `rentritz-landing/index.html` | DM Sans | **2185-line near-duplicate of `core/landing.html`**, differs by only 34 lines |
| — (separate Vite app) | `landing/App.jsx` | **Cormorant Garamond** + DM Sans | own `@import` injected from JS |

### System D — transactional email (7 templates)
`email/*.html`. Self-contained inline CSS, system font stacks, 14–21 hex each.
**Email HTML cannot use external stylesheets or CSS variables reliably** — these
are a legitimate exception and should be excluded from any migration.

---

## 2. Fonts

### Every font load, with file and line

| File | Line | Loads |
|---|---|---|
| [static/css/main.css:1](static/css/main.css:1) | 1 | `@import` DM Sans 300–600 |
| [static/css/admin.css:1](static/css/admin.css:1) | 1 | `@import` Inter 300–900 |
| [templates/base.html:14](templates/base.html:14) | 14 | `<link>` DM Sans 300–700 |
| [templates/admin/base_admin.html:9](templates/admin/base_admin.html:9) | 9 | `<link>` Inter 300–900 |
| [templates/core/landing.html:11](templates/core/landing.html:11) | 11 | `<link>` DM Sans + italics |
| [templates/core/for_lawyers.html:8](templates/core/for_lawyers.html:8) | 8 | `<link>` DM Sans 300–600 |
| [rentritz-landing/index.html:11](rentritz-landing/index.html:11) | 11 | `<link>` DM Sans + italics |
| [landing/App.jsx:16](landing/App.jsx:16) | 16 | `@import` **Cormorant Garamond** + DM Sans, injected at runtime |

**8 separate font loads for what should be one.** DM Sans is fetched by five
different declarations with four different weight sets.

### 🔴 Playfair Display is declared but never loaded

`'Playfair Display', Georgia, serif` appears **16 times** in
`static/css/main.css`, but **no `<link>`, `@import`, or `@font-face` anywhere in
the repo loads it** (verified). Every heading using it silently falls back to
**Georgia**. So the public app's real typography today is *DM Sans + Georgia*,
not the intended *DM Sans + Playfair*. This is a live rendering bug, not just an
inconsistency.

### Distinct `font-family` values in use

| Count | Value |
|---|---|
| 101 | `'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` |
| 19 | `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` |
| 16 | `'Playfair Display', Georgia, serif` ← **never loaded** |
| 9 | `monospace` |
| 6 | bare `-apple-system, …` system stacks (email templates) |
| 5 | `inherit` |
| 4 | four more DM Sans stacks with *different fallback chains* |

`font-family` is redeclared **178 times** across 27 files.

---

## 3. Colour

**607 raw hex codes across 36 files.** (Counted after stripping HTML entities —
`&#10003;`, `&#9733;` etc. otherwise produce false positives like `#10003`.)
**85 distinct hex values** for what is conceptually a ~12-colour palette.

> *Corrected on re-audit.* An earlier pass reported 605 / 35 files / 102 distinct.
> Two corrections: (a) `static/manifest.json` was missed — it carries 2 hex values
> (`theme_color`, `background_color`) and is design-relevant, giving 607 across 36
> files; (b) the 102 distinct figure still counted HTML entities — the strip was
> applied to occurrences but not to the distinct set, so `#10003`, `#9733`, `#9675`,
> `#8594`, `#8599`, `#8592` and similar were inflating it. The true distinct count
> is **85**. Every hex, with file and line, is listed in **Appendix A**.

Full per-file counts:

| Count | File |
|---|---|
| 85 | `static/css/main.css` |
| 58 | `templates/core/landing.html` |
| 58 | `rentritz-landing/index.html` |
| 43 | `templates/core/for_lawyers.html` |
| 25 | `templates/core/dashboard.html` |
| 24 | `templates/core/privacy.html` |
| 22 | `templates/lawyers/profile.html` |
| 22 | `static/css/admin.css` |
| 21 | `templates/email/lawyer_submitted.html` |
| 19 | `templates/admin/login.html` |
| 18 | `templates/lawyers/dashboard.html` |
| 17 | `templates/core/answer.html` |
| 16 | `templates/lawyers/browse.html` |
| 15 | `templates/email/welcome.html`, `email/lawyer_verified.html`, `email/lawyer_rejected.html`, `core/credits.html` |
| 14 | `templates/email/verify_email.html`, `email/reset_password.html` |
| 13 | `templates/core/terms.html` |
| 12 | `templates/core/history.html` |
| 10 | `lawyers/review.html`, `lawyers/register.html`, `lawyers/edit_profile.html` |
| 9 | `landing/App.jsx` |
| 8 | `templates/core/wizard.html` |
| 4 | `templates/lawyers/login.html` |
| 3 | `templates/auth/login.html` |
| 2 | `auth/reset_password.html`, `auth/register.html`, `admin/dashboard.html`, `static/manifest.json` |
| 1 | `base.html`, `admin/lawyers_list.html`, `admin/lawyer_detail.html`, `admin/base_admin.html` |

### Most-repeated raw values

| Count | Hex | Should be |
|---|---|---|
| 55 | `#fff` | `var(--white)` |
| 44 | `#f59e0b` | admin `var(--amber)` |
| 40 | `#1c1916` | `var(--charcoal)` / `var(--ink)` |
| 32 | `#f8f6f2` | `var(--off-white)` / `var(--paper)` |
| 31 | `#ffffff` | `var(--white)` — same colour as `#fff` above, written two ways |
| 27 | `#e5e5e5` | *no token exists* |
| 26 | `#2a2a2a` | admin `var(--dark-line)` |
| 26 | `#000` | *no token exists* |
| 24 | `#c8820a` | public `var(--amber)` |
| 16 | `#555`, `#1a1a1a`, `#0f0f0f` | partially tokenised |

### 🔴 Three competing `:root` blocks

There is no single source of truth. Three files define overlapping palettes under
**colliding variable names with different values**:

| Variable | `main.css` | `admin.css` | `landing.html` |
|---|---|---|---|
| `--amber` | `#c8820a` | **`#f59e0b`** | `#c8820a` |
| `--amber-dark` | `#b8720a` | **`#d97706`** | — |
| `--black` | `#0d0b09` | **`#0a0a0a`** | — |
| `--near-black` | `#1c1916` | **`#111111`** | — |
| `--dark-card` | `var(--white)` | **`#1a1a1a`** | — |
| `--dark-line` | `rgba(58,53,48,0.12)` | **`#2a2a2a`** | — |
| `--off-white` | `#f8f6f2` | **`#f8f7f4`** | `--paper: #f8f6f2` |
| `--text-muted` | `#9a8f82` | **`#888888`** | `--dim: #9a8f82` |
| `--text-light` | `#9a8f82` | **`#aaaaaa`** | — |

`--dark-card` is the sharpest example: **white** in the public app, **`#1a1a1a`**
in admin. Same name, inverted meaning.

`landing.html` additionally renames the *same* colours a third time:
`--paper`/`--ink`/`--muted`/`--dim`/`--rule` are the `main.css`
`--off-white`/`--charcoal`/`--mid-grey`/`--warm-grey`/`--border` values under new
names.

### Components defining their own colours locally
Every file in the hex table above with an inline `<style>` block — **20
templates** — defines colours locally rather than referencing tokens. The worst:
`core/landing.html`, `core/for_lawyers.html`, `core/dashboard.html`,
`lawyers/profile.html`, `admin/login.html`.

---

## 4. Arbitrary values

**Not applicable.** This concept is Tailwind-specific (`text-[15px]`,
`bg-[#fff]`). There is no Tailwind in this project, so there are zero arbitrary
Tailwind values. The equivalent problem here is raw hex + magic pixel values in
inline `<style>` blocks, quantified in §3 and §5.

## 5. Shadows, radii, transitions

| Property | Distinct values found | In a token | Verdict |
|---|---|---|---|
| `border-radius` | **45** | 4 (`--radius` 12px, `--radius-sm` 8px, `--radius-lg` 20px, + `999px` pill) | 35 raw literals: `2px 3px 4px 5px 6px 8px 9px 10px 12px 14px 16px 18px 20px 50px 100px 999px 50%` |
| `box-shadow` | **38** | 5 (`--shadow`, `-sm`, `-md`, `-lg`, `-amber`) | 33 one-off literals, e.g. `0 30px 60px -20px rgba(14,12,10,0.30), 0 12px 28px -12px rgba(14,12,10,0.18)` |
| `transition` | **130** | 1 (`--transition`) | 129 ad-hoc durations/easings |

Notably `8px` (37×), `50%` (36×), `999px` (27×), `6px` (19×) and `12px` (19×) are
all written as literals even though `--radius`/`--radius-sm` exist and are used
elsewhere (35× and 15×) — i.e. the tokens exist and are simply bypassed.

Easing functions in use include at least `cubic-bezier(0.4,0,0.2,1)` (main.css)
and `cubic-bezier(0.22,1,0.36,1)` (landing `--ease`) — two different house curves.

---

## 6. Structural duplication

- `rentritz-landing/index.html` is a **2185-line near-copy** of
  `templates/core/landing.html`, differing by 34 lines. It is not served by any
  Flask route. Two copies of the largest design surface in the app will drift.
- `landing/` is a third landing implementation — a React/Vite app using
  **Cormorant Garamond**, a serif used nowhere else.

---

## 7. Ranked migration order

By user traffic, highest first. (Sequencing only — **not** a commitment to any
token scheme, which is still blocked.)

1. `core/landing.html` — `/`, every visitor, largest file, own design system
2. `core/dashboard.html` — every logged-in user
3. `core/wizard.html` — `/consult/<slug>`, core journey
4. `core/answer.html` — core journey
5. `lawyers/browse.html`
6. `lawyers/profile.html`
7. `auth/login.html` + `auth/register.html`
8. `core/credits.html`
9. `core/history.html`
10. `core/for_lawyers.html` — own design system
11. `lawyers/dashboard.html`
12. `lawyers/edit_profile.html`
13. `lawyers/register.html` + `lawyers/login.html`
14. `lawyers/review.html`
15. `auth/forgot_password.html` + `auth/reset_password.html`
16. `core/terms.html` + `core/privacy.html`
17. `errors/*` — already clean, verify only
18. `admin/*` (19 templates) — **blocked on the dark-mode question**
19. `email/*` (7 templates) — **recommend excluding**, email HTML needs inline CSS
20. `rentritz-landing/`, `landing/` — **recommend deleting or routing**, not migrating

---

## 8. Questions for you

Logged here per the brief rather than guessed at.

1. **Which codebase was the token spec written for?** `chilli`/`crop`/`ember`/
   `ink`/`coorg`, Hanken Grotesk, Bricolage Grotesque, Kannada and `src/` all
   point to a different, Tailwind-based, India-focused project. This repo is
   Flask/Jinja and Dubai-focused.

2. **Do you want that design system introduced here, or the existing one
   consolidated?** These are very different jobs:
   - *(a) Adopt the brief's system* — means adding Tailwind, a build step, new
     fonts, and restyling all 53 templates. That is a redesign, and it changes
     how CSS is delivered.
   - *(b) Consolidate what exists* — collapse the three `:root` blocks into one,
     fix the Playfair bug, replace 605 raw hexes with the existing variables,
     unify 8 font loads into 1. Presentation-only, no new dependencies, fits
     every other rule in your brief. **This is what I'd recommend**, and the
     audit above is already the work plan for it.

3. **Admin dark theme** — the brief says light-mode only, but 19 admin templates
   are deliberately dark. Convert to light, or is admin an intentional exception?

4. **`rentritz-landing/` and `landing/`** — duplicate/unrouted landing pages.
   Delete, or keep in sync? Deleting is out of scope for a presentation-only
   refactor, so I have left both alone.

5. **Email templates** — confirm these are excluded; inline CSS is required for
   email client compatibility, so token variables cannot be used there.

No code has been modified. Awaiting your direction before Phase 1.

---

## 9. Two further concrete findings from the re-audit

**9.1 — The public app advertises the *admin* amber to the browser.**
`templates/base.html:12` sets `<meta name="theme-color" content="#f59e0b">`.
That is `admin.css`'s amber, not the public app's `#c8820a`. On mobile the browser
chrome around every public page is tinted with the admin accent. One-line fix, but it
depends on resolving which amber is canonical (Question 2 below).

**9.2 — `static/manifest.json` is a fourth, unmanaged colour surface.**
The PWA manifest carries its own `theme_color` and `background_color`. No stylesheet
governs it and no audit rule in the brief covers it, but it is user-visible on install.

---

# Appendix A — every raw hex code, with file and line

607 occurrences across 36 files, grouped one entry per source line.
HTML entities (`&#10003;` etc.) excluded. Generated, not hand-written.

- `templates/admin/base_admin.html:51` — #f59e0b
- `templates/admin/dashboard.html:320` — #fff
- `templates/admin/dashboard.html:642` — #f59e0b
- `templates/admin/lawyers_list.html:80` — #818cf8
- `templates/admin/lawyer_detail.html:15` — #818cf8
- `templates/admin/login.html:9` — #0f0f0f, #fff
- `templates/admin/login.html:10` — #1a1a1a, #2a2a2a
- `templates/admin/login.html:11` — #f59e0b
- `templates/admin/login.html:13` — #666
- `templates/admin/login.html:14` — #aaa
- `templates/admin/login.html:15` — #111, #333, #fff
- `templates/admin/login.html:16` — #f59e0b
- `templates/admin/login.html:17` — #f59e0b, #000
- `templates/admin/login.html:18` — #d97706
- `templates/admin/login.html:19` — #3b0000, #7f1d1d, #fca5a5
- `templates/admin/login.html:22` — #555
- `templates/admin/login.html:23` — #f59e0b
- `templates/auth/login.html:11` — #555
- `templates/auth/login.html:14` — #f59e0b
- `templates/auth/login.html:59` — #555
- `templates/auth/register.html:11` — #555
- `templates/auth/register.html:14` — #f59e0b
- `templates/auth/reset_password.html:11` — #555
- `templates/auth/reset_password.html:14` — #f59e0b
- `templates/base.html:12` — #f59e0b
- `templates/core/answer.html:8` — #f8f6f2
- `templates/core/answer.html:9` — #f0ece6
- `templates/core/answer.html:10` — #ffffff
- `templates/core/answer.html:11` — #c8820a
- `templates/core/answer.html:12` — #b8720a
- `templates/core/answer.html:13` — #1c1916
- `templates/core/answer.html:26` — #0d0d0d
- `templates/core/answer.html:83` — #ffffff
- `templates/core/answer.html:160` — #000
- `templates/core/answer.html:171` — #16a34a, #fff
- `templates/core/answer.html:393` — #000
- `templates/core/answer.html:394` — #000
- `templates/core/answer.html:404` — #000
- `templates/core/answer.html:405` — #fff
- `templates/core/answer.html:414` — #1a1a1a
- `templates/core/answer.html:447` — #000
- `templates/core/credits.html:11` — #f8f6f2
- `templates/core/credits.html:12` — #f0ece6
- `templates/core/credits.html:13` — #ffffff
- `templates/core/credits.html:14` — #f0ece6
- `templates/core/credits.html:15` — #f59e0b
- `templates/core/credits.html:16` — #d97706
- `templates/core/credits.html:17` — #1c1916
- `templates/core/credits.html:18` — #6b6157
- `templates/core/credits.html:19` — #9a8f82
- `templates/core/credits.html:211` — #000
- `templates/core/credits.html:257` — #000
- `templates/core/credits.html:362` — #4ade80
- `templates/core/credits.html:363` — #f87171
- `templates/core/credits.html:408` — #000
- `templates/core/credits.html:415` — #000
- `templates/core/dashboard.html:11` — #f8f6f2
- `templates/core/dashboard.html:12` — #f0ece6
- `templates/core/dashboard.html:13` — #ffffff
- `templates/core/dashboard.html:14` — #f0ece6
- `templates/core/dashboard.html:15` — #c8820a
- `templates/core/dashboard.html:16` — #b8720a
- `templates/core/dashboard.html:17` — #1c1916
- `templates/core/dashboard.html:18` — #6b6259
- `templates/core/dashboard.html:19` — #9a8f82
- `templates/core/dashboard.html:158` — #fff
- `templates/core/dashboard.html:420` — #4ade80
- `templates/core/dashboard.html:639` — #4ade80, #f87171
- `templates/core/dashboard.html:732` — #111111
- `templates/core/dashboard.html:756` — #f59e0b
- `templates/core/dashboard.html:768` — #ffffff
- `templates/core/dashboard.html:777` — #888888
- `templates/core/dashboard.html:815` — #f59e0b
- `templates/core/dashboard.html:821` — #f59e0b
- `templates/core/dashboard.html:837` — #ffffff
- `templates/core/dashboard.html:844` — #888888
- `templates/core/dashboard.html:852` — #f59e0b
- `templates/core/dashboard.html:853` — #000000
- `templates/core/dashboard.html:869` — #d97706
- `templates/core/dashboard.html:879` — #555555
- `templates/core/for_lawyers.html:12` — #f8f6f2, #1c1916
- `templates/core/for_lawyers.html:17` — #fff
- `templates/core/for_lawyers.html:18` — #1c1916
- `templates/core/for_lawyers.html:19` — #f5a623
- `templates/core/for_lawyers.html:20` — #c8820a
- `templates/core/for_lawyers.html:23` — #3a3530
- `templates/core/for_lawyers.html:24` — #c8820a, #fff
- `templates/core/for_lawyers.html:26` — #1c1916, #2a2018, #1c1916
- `templates/core/for_lawyers.html:30` — #f5a623
- `templates/core/for_lawyers.html:31` — #fff
- `templates/core/for_lawyers.html:32` — #f5a623
- `templates/core/for_lawyers.html:36` — #c8820a, #fff
- `templates/core/for_lawyers.html:37` — #b8720a
- `templates/core/for_lawyers.html:38` — #fff
- `templates/core/for_lawyers.html:43` — #1c1916
- `templates/core/for_lawyers.html:44` — #9a8f82
- `templates/core/for_lawyers.html:48` — #fff, #c8820a
- `templates/core/for_lawyers.html:49` — #c8820a
- `templates/core/for_lawyers.html:50` — #1c1916
- `templates/core/for_lawyers.html:51` — #9a8f82
- `templates/core/for_lawyers.html:52` — #f2ede6
- `templates/core/for_lawyers.html:54` — #fff
- `templates/core/for_lawyers.html:56` — #1c1916
- `templates/core/for_lawyers.html:57` — #9a8f82
- `templates/core/for_lawyers.html:58` — #f8f6f2
- `templates/core/for_lawyers.html:61` — #fff, #1c1916
- `templates/core/for_lawyers.html:62` — #c8820a
- `templates/core/for_lawyers.html:66` — #6b6259
- `templates/core/for_lawyers.html:67` — #c8820a
- `templates/core/for_lawyers.html:70` — #fff
- `templates/core/for_lawyers.html:72` — #fff, #b8720a
- `templates/core/for_lawyers.html:74` — #1c1916
- `templates/core/for_lawyers.html:76` — #fff
- `templates/core/for_lawyers.html:77` — #f5a623
- `templates/core/for_lawyers.html:79` — #f5a623
- `templates/core/history.html:11` — #f8f6f2
- `templates/core/history.html:12` — #f0ece6
- `templates/core/history.html:13` — #ffffff
- `templates/core/history.html:14` — #f0ece6
- `templates/core/history.html:15` — #c8820a
- `templates/core/history.html:16` — #b8720a
- `templates/core/history.html:17` — #1c1916
- `templates/core/history.html:18` — #6b6259
- `templates/core/history.html:19` — #9a8f82
- `templates/core/history.html:196` — #4ade80
- `templates/core/history.html:252` — #000
- `templates/core/history.html:325` — #4ade80
- `templates/core/landing.html:20` — #f8f6f2
- `templates/core/landing.html:21` — #f0ece6
- `templates/core/landing.html:22` — #ffffff
- `templates/core/landing.html:23` — #1c1916
- `templates/core/landing.html:24` — #0e0c0a
- `templates/core/landing.html:25` — #0a0807
- `templates/core/landing.html:26` — #1c1916
- `templates/core/landing.html:27` — #c8820a
- `templates/core/landing.html:28` — #e0a040
- `templates/core/landing.html:29` — #a86a08
- `templates/core/landing.html:30` — #6b6157
- `templates/core/landing.html:31` — #9a8f82
- `templates/core/landing.html:51` — #fff
- `templates/core/landing.html:77` — #000
- `templates/core/landing.html:83` — #d68b0c
- `templates/core/landing.html:93` — #0a0807
- `templates/core/landing.html:116` — #fff, #fff
- `templates/core/landing.html:117` — #fff, #fff
- `templates/core/landing.html:162` — #fff
- `templates/core/landing.html:184` — #000
- `templates/core/landing.html:188` — #d68b0c, #000
- `templates/core/landing.html:190` — #fff
- `templates/core/landing.html:227` — #000
- `templates/core/landing.html:238` — #f8f6f2
- `templates/core/landing.html:305` — #000
- `templates/core/landing.html:312` — #fff
- `templates/core/landing.html:326` — #fff
- `templates/core/landing.html:360` — #fff
- `templates/core/landing.html:424` — #f8f6f2
- `templates/core/landing.html:549` — #f8f6f2
- `templates/core/landing.html:589` — #f8f6f2
- `templates/core/landing.html:707` — #0e0c0a
- `templates/core/landing.html:715` — #1c1916, #0a0807
- `templates/core/landing.html:731` — #1c1916, #0a0807
- `templates/core/landing.html:741` — #f8f6f2
- `templates/core/landing.html:756` — #fff
- `templates/core/landing.html:779` — #fff
- `templates/core/landing.html:793` — #fff
- `templates/core/landing.html:856` — #1c1916, #0a0807
- `templates/core/landing.html:859` — #f8f6f2
- `templates/core/landing.html:883` — #c8820a, #e0a040
- `templates/core/landing.html:885` — #fff
- `templates/core/landing.html:920` — #c8820a, #e0a040
- `templates/core/landing.html:929` — #1c1916
- `templates/core/landing.html:930` — #1c1916
- `templates/core/landing.html:941` — #1c1916
- `templates/core/landing.html:966` — #f8f6f2
- `templates/core/landing.html:999` — #fff
- `templates/core/landing.html:1032` — #0a0807, #f8f6f2
- `templates/core/privacy.html:8` — #0a0a0a
- `templates/core/privacy.html:9` — #e5e5e5
- `templates/core/privacy.html:21` — #f59e0b
- `templates/core/privacy.html:28` — #ffffff
- `templates/core/privacy.html:34` — #555
- `templates/core/privacy.html:37` — #1e1e1e
- `templates/core/privacy.html:45` — #ffffff
- `templates/core/privacy.html:50` — #1e1e1e
- `templates/core/privacy.html:55` — #a3a3a3
- `templates/core/privacy.html:66` — #a3a3a3
- `templates/core/privacy.html:72` — #1e1e1e
- `templates/core/privacy.html:81` — #444
- `templates/core/privacy.html:84` — #f59e0b
- `templates/core/privacy.html:114` — #e5e5e5
- `templates/core/privacy.html:119` — #e5e5e5
- `templates/core/privacy.html:124` — #e5e5e5
- `templates/core/privacy.html:130` — #e5e5e5
- `templates/core/privacy.html:163` — #e5e5e5
- `templates/core/privacy.html:167` — #e5e5e5
- `templates/core/privacy.html:171` — #e5e5e5
- `templates/core/privacy.html:202` — #e5e5e5
- `templates/core/privacy.html:207` — #e5e5e5
- `templates/core/privacy.html:256` — #e5e5e5
- `templates/core/privacy.html:257` — #f59e0b
- `templates/core/terms.html:8` — #0a0a0a
- `templates/core/terms.html:9` — #e5e5e5
- `templates/core/terms.html:21` — #f59e0b
- `templates/core/terms.html:28` — #ffffff
- `templates/core/terms.html:34` — #555
- `templates/core/terms.html:37` — #1e1e1e
- `templates/core/terms.html:45` — #ffffff
- `templates/core/terms.html:50` — #1e1e1e
- `templates/core/terms.html:55` — #a3a3a3
- `templates/core/terms.html:66` — #a3a3a3
- `templates/core/terms.html:72` — #1e1e1e
- `templates/core/terms.html:81` — #444
- `templates/core/terms.html:84` — #f59e0b
- `templates/core/wizard.html:8` — #f8f6f2
- `templates/core/wizard.html:9` — #ffffff
- `templates/core/wizard.html:10` — #f0ece6
- `templates/core/wizard.html:11` — #c8820a
- `templates/core/wizard.html:12` — #b8720a
- `templates/core/wizard.html:13` — #1c1916
- `templates/core/wizard.html:235` — #3a3530
- `templates/core/wizard.html:287` — #fff
- `templates/email/lawyer_rejected.html:8` — #0f0f0f, #e5e5e5
- `templates/email/lawyer_rejected.html:10` — #1a1a1a, #2a2a2a
- `templates/email/lawyer_rejected.html:12` — #f59e0b
- `templates/email/lawyer_rejected.html:13` — #ffffff
- `templates/email/lawyer_rejected.html:14` — #a3a3a3
- `templates/email/lawyer_rejected.html:15` — #1f0f0f
- `templates/email/lawyer_rejected.html:16` — #ef4444
- `templates/email/lawyer_rejected.html:17` — #e5e5e5
- `templates/email/lawyer_rejected.html:18` — #f59e0b, #0f0f0f
- `templates/email/lawyer_rejected.html:19` — #2a2a2a
- `templates/email/lawyer_rejected.html:20` — #6b6b6b
- `templates/email/lawyer_rejected.html:21` — #444
- `templates/email/lawyer_submitted.html:8` — #0f0f0f, #e5e5e5
- `templates/email/lawyer_submitted.html:10` — #1a1a1a, #2a2a2a
- `templates/email/lawyer_submitted.html:12` — #f59e0b
- `templates/email/lawyer_submitted.html:13` — #ffffff
- `templates/email/lawyer_submitted.html:14` — #a3a3a3
- `templates/email/lawyer_submitted.html:15` — #1c1007, #f59e0b, #f59e0b
- `templates/email/lawyer_submitted.html:16` — #2a2a2a
- `templates/email/lawyer_submitted.html:18` — #6b6b6b
- `templates/email/lawyer_submitted.html:19` — #e5e5e5
- `templates/email/lawyer_submitted.html:20` — #f59e0b, #0f0f0f
- `templates/email/lawyer_submitted.html:21` — #2a2a2a
- `templates/email/lawyer_submitted.html:22` — #6b6b6b
- `templates/email/lawyer_submitted.html:23` — #444
- `templates/email/lawyer_submitted.html:39` — #ffffff
- `templates/email/lawyer_submitted.html:48` — #111, #2a2a2a
- `templates/email/lawyer_verified.html:8` — #0f0f0f, #e5e5e5
- `templates/email/lawyer_verified.html:10` — #1a1a1a, #2a2a2a
- `templates/email/lawyer_verified.html:12` — #f59e0b
- `templates/email/lawyer_verified.html:13` — #ffffff
- `templates/email/lawyer_verified.html:14` — #a3a3a3
- `templates/email/lawyer_verified.html:15` — #052e16, #22c55e, #22c55e
- `templates/email/lawyer_verified.html:16` — #f59e0b, #0f0f0f
- `templates/email/lawyer_verified.html:17` — #2a2a2a
- `templates/email/lawyer_verified.html:18` — #6b6b6b
- `templates/email/lawyer_verified.html:19` — #444
- `templates/email/reset_password.html:10` — #0f0f0f
- `templates/email/reset_password.html:12` — #e5e5e5
- `templates/email/reset_password.html:20` — #1a1a1a
- `templates/email/reset_password.html:21` — #2a2a2a
- `templates/email/reset_password.html:33` — #f59e0b
- `templates/email/reset_password.html:38` — #ffffff
- `templates/email/reset_password.html:44` — #a3a3a3
- `templates/email/reset_password.html:49` — #f59e0b
- `templates/email/reset_password.html:50` — #0f0f0f
- `templates/email/reset_password.html:60` — #2a2a2a
- `templates/email/reset_password.html:65` — #6b6b6b
- `templates/email/reset_password.html:69` — #a3a3a3
- `templates/email/reset_password.html:76` — #444
- `templates/email/reset_password.html:97` — #e5e5e5
- `templates/email/verify_email.html:10` — #0f0f0f
- `templates/email/verify_email.html:12` — #e5e5e5
- `templates/email/verify_email.html:20` — #1a1a1a
- `templates/email/verify_email.html:21` — #2a2a2a
- `templates/email/verify_email.html:33` — #f59e0b
- `templates/email/verify_email.html:38` — #ffffff
- `templates/email/verify_email.html:44` — #a3a3a3
- `templates/email/verify_email.html:49` — #f59e0b
- `templates/email/verify_email.html:50` — #0f0f0f
- `templates/email/verify_email.html:60` — #2a2a2a
- `templates/email/verify_email.html:65` — #6b6b6b
- `templates/email/verify_email.html:69` — #a3a3a3
- `templates/email/verify_email.html:76` — #444
- `templates/email/verify_email.html:96` — #e5e5e5
- `templates/email/welcome.html:10` — #0f0f0f
- `templates/email/welcome.html:12` — #e5e5e5
- `templates/email/welcome.html:20` — #1a1a1a
- `templates/email/welcome.html:21` — #2a2a2a
- `templates/email/welcome.html:33` — #f59e0b
- `templates/email/welcome.html:38` — #ffffff
- `templates/email/welcome.html:44` — #a3a3a3
- `templates/email/welcome.html:49` — #292318
- `templates/email/welcome.html:50` — #f59e0b
- `templates/email/welcome.html:51` — #f59e0b
- `templates/email/welcome.html:60` — #f59e0b
- `templates/email/welcome.html:61` — #0f0f0f
- `templates/email/welcome.html:71` — #2a2a2a
- `templates/email/welcome.html:76` — #6b6b6b
- `templates/email/welcome.html:83` — #444
- `templates/lawyers/browse.html:8` — #f8f6f2
- `templates/lawyers/browse.html:9` — #ffffff
- `templates/lawyers/browse.html:10` — #f0ece6
- `templates/lawyers/browse.html:11` — #c8820a
- `templates/lawyers/browse.html:12` — #b8720a
- `templates/lawyers/browse.html:13` — #1c1916
- `templates/lawyers/browse.html:14` — #6b6259
- `templates/lawyers/browse.html:15` — #9a8f82
- `templates/lawyers/browse.html:66` — #ffffff
- `templates/lawyers/browse.html:68` — #1c1916
- `templates/lawyers/browse.html:89` — #fff
- `templates/lawyers/browse.html:96` — #000
- `templates/lawyers/browse.html:119` — #ffffff
- `templates/lawyers/browse.html:121` — #1c1916
- `templates/lawyers/browse.html:126` — #000
- `templates/lawyers/browse.html:187` — #10b981
- `templates/lawyers/dashboard.html:9` — #f8f6f2, #ffffff, #f0ece6
- `templates/lawyers/dashboard.html:10` — #c8820a, #b8720a, #1c1916
- `templates/lawyers/dashboard.html:11` — #6b6259, #9a8f82
- `templates/lawyers/dashboard.html:30` — #fff
- `templates/lawyers/dashboard.html:58` — #f87171
- `templates/lawyers/dashboard.html:59` — #4ade80
- `templates/lawyers/dashboard.html:88` — #4ade80
- `templates/lawyers/dashboard.html:96` — #4ade80
- `templates/lawyers/dashboard.html:120` — #4ade80
- `templates/lawyers/dashboard.html:122` — #60a5fa
- `templates/lawyers/dashboard.html:376` — #4ade80
- `templates/lawyers/dashboard.html:381` — #4ade80
- `templates/lawyers/dashboard.html:485` — #4ade80
- `templates/lawyers/edit_profile.html:8` — #f8f6f2, #ffffff, #c8820a, #b8720a
- `templates/lawyers/edit_profile.html:9` — #1c1916, #6b6259, #9a8f82
- `templates/lawyers/edit_profile.html:31` — #f87171
- `templates/lawyers/edit_profile.html:47` — #000
- `templates/lawyers/edit_profile.html:216` — #f87171
- `templates/lawyers/login.html:11` — #555
- `templates/lawyers/login.html:14` — #f59e0b
- `templates/lawyers/login.html:19` — #f59e0b
- `templates/lawyers/login.html:59` — #555
- `templates/lawyers/profile.html:8` — #f8f6f2, #ffffff, #f0ece6
- `templates/lawyers/profile.html:9` — #c8820a, #b8720a, #1c1916
- `templates/lawyers/profile.html:10` — #6b6259, #9a8f82
- `templates/lawyers/profile.html:52` — #4ade80
- `templates/lawyers/profile.html:54` — #60a5fa
- `templates/lawyers/profile.html:105` — #fff
- `templates/lawyers/profile.html:123` — #10b981
- `templates/lawyers/profile.html:160` — #4ade80
- `templates/lawyers/profile.html:328` — #f87171
- `templates/lawyers/profile.html:483` — #f87171
- `templates/lawyers/profile.html:523` — #f59e0b, #555
- `templates/lawyers/profile.html:528` — #f59e0b, #555
- `templates/lawyers/profile.html:533` — #f59e0b, #555
- `templates/lawyers/profile.html:569` — #f87171
- `templates/lawyers/register.html:8` — #f8f6f2, #ffffff, #c8820a, #b8720a
- `templates/lawyers/register.html:9` — #1c1916, #6b6259, #9a8f82
- `templates/lawyers/register.html:42` — #f87171
- `templates/lawyers/register.html:79` — #000
- `templates/lawyers/register.html:282` — #f87171
- `templates/lawyers/review.html:8` — #f8f6f2
- `templates/lawyers/review.html:9` — #ffffff
- `templates/lawyers/review.html:10` — #c8820a
- `templates/lawyers/review.html:11` — #b8720a
- `templates/lawyers/review.html:12` — #1c1916
- `templates/lawyers/review.html:13` — #6b6259
- `templates/lawyers/review.html:14` — #9a8f82
- `templates/lawyers/review.html:178` — #000
- `templates/lawyers/review.html:223` — #ef4444
- `templates/lawyers/review.html:321` — #ef4444
- `static/css/admin.css:6` — #f59e0b
- `static/css/admin.css:7` — #d97706
- `static/css/admin.css:9` — #0a0a0a
- `static/css/admin.css:10` — #111111
- `static/css/admin.css:11` — #1a1a1a
- `static/css/admin.css:12` — #2a2a2a
- `static/css/admin.css:13` — #0f0f0f
- `static/css/admin.css:14` — #ffffff
- `static/css/admin.css:15` — #f8f7f4
- `static/css/admin.css:16` — #888888
- `static/css/admin.css:17` — #aaaaaa
- `static/css/admin.css:18` — #ef4444
- `static/css/admin.css:20` — #22c55e
- `static/css/admin.css:101` — #444
- `static/css/admin.css:131` — #818cf8
- `static/css/admin.css:132` — #f472b6
- `static/css/admin.css:135` — #38bdf8
- `static/css/admin.css:214` — #38bdf8
- `static/css/admin.css:223` — #3a3a3a
- `static/css/admin.css:241` — #38bdf8
- `static/css/admin.css:244` — #444
- `static/css/admin.css:300` — #3a3a3a
- `static/css/main.css:4` — #ffffff
- `static/css/main.css:5` — #f8f6f2
- `static/css/main.css:6` — #f2ede6
- `static/css/main.css:7` — #ebe4d8
- `static/css/main.css:8` — #9a8f82
- `static/css/main.css:9` — #6b6259
- `static/css/main.css:10` — #3a3530
- `static/css/main.css:11` — #1c1916
- `static/css/main.css:12` — #0d0b09
- `static/css/main.css:14` — #c8820a
- `static/css/main.css:15` — #f5a623
- `static/css/main.css:16` — #b8720a
- `static/css/main.css:26` — #1c1916
- `static/css/main.css:39` — #fef2f2
- `static/css/main.css:40` — #fca5a5
- `static/css/main.css:41` — #991b1b
- `static/css/main.css:42` — #f0fdf4
- `static/css/main.css:43` — #86efac
- `static/css/main.css:44` — #166534
- `static/css/main.css:218` — #fff
- `static/css/main.css:422` — #eee
- `static/css/main.css:970` — #f5f5f5
- `static/css/main.css:1283` — #e5e5e5
- `static/css/main.css:1291` — #fffbeb
- `static/css/main.css:1292` — #fde68a
- `static/css/main.css:1310` — #ddd
- `static/css/main.css:1368` — #e5e5e5
- `static/css/main.css:1424` — #dcfce7, #166534
- `static/css/main.css:1425` — #f5f5f5, #888
- `static/css/main.css:1426` — #fef9c3, #854d0e
- `static/css/main.css:1427` — #fee2e2, #991b1b
- `static/css/main.css:1438` — #e5e5e5
- `static/css/main.css:1454` — #e5e5e5
- `static/css/main.css:1455` — #fafafa
- `static/css/main.css:1457` — #f0f0f0
- `static/css/main.css:1459` — #fafafa
- `static/css/main.css:1472` — #0f0f0f
- `static/css/main.css:1473` — #ccc
- `static/css/main.css:1478` — #1a1a1a
- `static/css/main.css:1479` — #2a2a2a
- `static/css/main.css:1485` — #fff
- `static/css/main.css:1503` — #1a1a1a
- `static/css/main.css:1504` — #2a2a2a
- `static/css/main.css:1514` — #555
- `static/css/main.css:1522` — #fff
- `static/css/main.css:1527` — #1a1a1a
- `static/css/main.css:1528` — #2a2a2a
- `static/css/main.css:1534` — #aaa
- `static/css/main.css:1542` — #111
- `static/css/main.css:1543` — #2a2a2a
- `static/css/main.css:1545` — #eee
- `static/css/main.css:1559` — #1a1a1a
- `static/css/main.css:1560` — #2a2a2a
- `static/css/main.css:1566` — #141414
- `static/css/main.css:1567` — #555
- `static/css/main.css:1568` — #2a2a2a
- `static/css/main.css:1570` — #aaa, #1e1e1e
- `static/css/main.css:1571` — #1e1e1e
- `static/css/main.css:1577` — #0f0f0f
- `static/css/main.css:1586` — #1a1a1a
- `static/css/main.css:1587` — #2a2a2a
- `static/css/main.css:1598` — #fff
- `static/css/main.css:1605` — #444
- `static/css/main.css:1610` — #666
- `static/css/main.css:1615` — #111
- `static/css/main.css:1616` — #2a2a2a
- `static/css/main.css:1618` — #eee
- `static/css/main.css:1632` — #111
- `static/css/main.css:1633` — #2a2a2a
- `static/css/main.css:1641` — #1a1a1a
- `static/css/main.css:1642` — #2a2a2a
- `static/css/main.css:1649` — #ddd
- `static/css/main.css:1650` — #555
- `static/css/main.css:1657` — #111
- `static/css/main.css:1661` — #888
- `static/css/main.css:1664` — #555
- `static/css/main.css:1707` — #d0cdc8
- `static/css/main.css:1798` — #d0cdc8
- `static/css/main.css:1846` — #e5e5e5
- `static/css/main.css:1860` — #d0cdc8
- `static/manifest.json:8` — #0a0a0a
- `static/manifest.json:9` — #f59e0b
- `landing/App.jsx:8` — #c9a227, #f59e0b
- `landing/App.jsx:9` — #0a0a0a, #111111, #1a1a1a
- `landing/App.jsx:10` — #faf8f3
- `landing/App.jsx:19` — #0a0a0a, #faf8f3
- `landing/App.jsx:21` — #faf8f3
- `rentritz-landing/index.html:20` — #f8f6f2
- `rentritz-landing/index.html:21` — #f0ece6
- `rentritz-landing/index.html:22` — #ffffff
- `rentritz-landing/index.html:23` — #1c1916
- `rentritz-landing/index.html:24` — #0e0c0a
- `rentritz-landing/index.html:25` — #0a0807
- `rentritz-landing/index.html:26` — #1c1916
- `rentritz-landing/index.html:27` — #c8820a
- `rentritz-landing/index.html:28` — #e0a040
- `rentritz-landing/index.html:29` — #a86a08
- `rentritz-landing/index.html:30` — #6b6157
- `rentritz-landing/index.html:31` — #9a8f82
- `rentritz-landing/index.html:51` — #fff
- `rentritz-landing/index.html:77` — #000
- `rentritz-landing/index.html:83` — #d68b0c
- `rentritz-landing/index.html:93` — #0a0807
- `rentritz-landing/index.html:116` — #fff, #fff
- `rentritz-landing/index.html:117` — #fff, #fff
- `rentritz-landing/index.html:162` — #fff
- `rentritz-landing/index.html:184` — #000
- `rentritz-landing/index.html:188` — #d68b0c, #000
- `rentritz-landing/index.html:190` — #fff
- `rentritz-landing/index.html:227` — #000
- `rentritz-landing/index.html:238` — #f8f6f2
- `rentritz-landing/index.html:305` — #000
- `rentritz-landing/index.html:312` — #fff
- `rentritz-landing/index.html:326` — #fff
- `rentritz-landing/index.html:360` — #fff
- `rentritz-landing/index.html:424` — #f8f6f2
- `rentritz-landing/index.html:549` — #f8f6f2
- `rentritz-landing/index.html:589` — #f8f6f2
- `rentritz-landing/index.html:707` — #0e0c0a
- `rentritz-landing/index.html:715` — #1c1916, #0a0807
- `rentritz-landing/index.html:731` — #1c1916, #0a0807
- `rentritz-landing/index.html:741` — #f8f6f2
- `rentritz-landing/index.html:756` — #fff
- `rentritz-landing/index.html:779` — #fff
- `rentritz-landing/index.html:793` — #fff
- `rentritz-landing/index.html:856` — #1c1916, #0a0807
- `rentritz-landing/index.html:859` — #f8f6f2
- `rentritz-landing/index.html:883` — #c8820a, #e0a040
- `rentritz-landing/index.html:885` — #fff
- `rentritz-landing/index.html:920` — #c8820a, #e0a040
- `rentritz-landing/index.html:929` — #1c1916
- `rentritz-landing/index.html:930` — #1c1916
- `rentritz-landing/index.html:941` — #1c1916
- `rentritz-landing/index.html:966` — #f8f6f2
- `rentritz-landing/index.html:999` — #fff
- `rentritz-landing/index.html:1032` — #0a0807, #f8f6f2
