# DESIGN_MIGRATION.md

Working checklist. **This file is the memory between sessions.**

**Decision:** consolidate the existing design. Invent nothing.
**Reference page:** `templates/core/landing.html` — all collisions resolve to its
current values.

> **Superseded 2026-08-12.** The consolidation brief above is history. The live
> plan is the **R1 Crimson** migration, Steps 1–7. Palette and rules are in the
> operator's brief; progress lives here.

**Status: Step 1 = no-op (premise disproved). Step 2 = DONE, two commits.
Step 3 = BLOCKED on the F7 decision below.**

| Commit | Step | Scope |
|---|---|---|
| `4280438` `style(tokens): create single colour source of truth` | pre | tokens.css + landing link + main.css alias map |
| `dfde279` `style(motion): adopt landing easing curve` | pre | C15 only — **see F7: overridden on 10 pages** |
| `c054ed9` `style(fonts): collapse four DM Sans loads into one` | 2 | tokens.css §0 + main.css + base.html + landing + for_lawyers |
| `91de61e` `style(fonts): drop the duplicate admin Inter load` | 2 | base_admin.html only; admin.css untouched |

### Decisions recorded
- **F2 — admin exempt.** `admin.css` untouched, confirmed.
- **F3 — easing adopted**, shipped as its own commit.
- **F4 — REJECTED.** `rentritz-landing/` and `landing/` **retained**. Deleting is
  unsafe while no deploy config exists in-repo to confirm what Render builds.
- **B5 — CLOSED as "deferred, blocked on deploy config."**
- **F1 — still blocked.** Font table below; no font load has been merged or
  deleted, and the font declaration has **not** been moved into `tokens.css`
  (step 4 awaits your approval).

---

## Scope (after revision)

**In scope:** 26 pages — 9 public, 4 auth, 7 lawyer, 6 error — plus
`static/css/main.css`. **398 raw hex across 21 files.**

**Permanently excluded:**
- **Email** — 7 templates, 94 hex. Email clients do not support CSS custom
  properties; inline hex is correct there.
- **Dark admin panel** — 18 templates + `static/css/admin.css`, 46 hex.
  **Named permanent exception to light-mode-only.** Stays dark, stays on Inter.

---

## Phase 1 — the token layer

### 1a. Structural finding that de-risks everything

**`templates/core/landing.html` does not load `main.css`.** It is fully
self-contained (own `:root`, own `<style>`, own font link). Therefore **no Phase 1
edit to `main.css` can alter the reference page** — "landing unchanged" is
provable by inspection rather than by eye.

`templates/core/for_lawyers.html` **does** load `main.css` (line 9) *and* carries
its own palette, so it inherits every change below.

### 1b. Collision table — mapped by ROLE, not by name

Merging by name would be wrong. Two examples: `main.css --near-black` is `#1c1916`,
identical to `--charcoal`, and is used as a **text** colour — it is *not* landing's
`--dark` (`#0a0807`, a section **background**). Mapped mechanically it would darken
text that should not change. Likewise `--cream` and `--paper-2` are the same role
under different names and different values.

| # | Role | **Winner (landing)** | `main.css` today | `admin.css` today | Visible change? |
|---|---|---|---|---|---|
| 1 | Accent | `--amber` **#c8820a** | `--amber` #c8820a | `--amber` #f59e0b *(exempt)* | **No** |
| 2 | Accent light | `--amber-soft` **#e0a040** | `--amber-light` #f5a623 | — | **Yes** — deeper, less yellow |
| 3 | Accent dark | `--amber-2` **#a86a08** | `--amber-dark` #b8720a | `--amber-dark` #d97706 *(exempt)* | **Yes** — slightly deeper |
| 4 | Page background | `--paper` **#f8f6f2** | `--off-white` #f8f6f2 | #f8f7f4 *(exempt)* | **No** |
| 5 | Sunken surface | `--paper-2` **#f0ece6** | `--cream` #f2ede6 | — | **Yes** — marginally cooler |
| 6 | Card surface | `--card` **#ffffff** | `--white` #ffffff | — | **No** |
| 7 | Body text | `--ink` **#1c1916** | `--charcoal` #1c1916 | — | **No** |
| 8 | Deepest ink | `--ink-2` **#0e0c0a** | `--black` #0d0b09 | #0a0a0a *(exempt)* | **Yes** — 1/255 per channel, imperceptible |
| 9 | Dark text | *maps to* `--ink` **#1c1916** | `--near-black` #1c1916 | #111111 *(exempt)* | **No** — same value, role-corrected |
| 10 | Secondary text | `--muted` **#6b6157** | `--mid-grey` #6b6259 | #888888 *(exempt)* | **Yes** — imperceptible |
| 11 | Tertiary text | `--dim` **#9a8f82** | `--warm-grey` #9a8f82 | #aaaaaa *(exempt)* | **No** |
| 12 | Border | `--rule` **rgba(58,53,48,0.12)** | `--border` rgba(58,53,48,0.12) | #2a2a2a *(exempt)* | **No** |
| 13 | Border soft | `--rule-soft` **rgba(58,53,48,0.06)** | — | — | **No** — new name, unused |
| 14 | Dark section bg | `--dark` **#0a0807** | — | — | **No** — landing-only role |
| 15 | Easing | `--ease` **cubic-bezier(0.22,1,0.36,1)** | `--transition` uses cubic-bezier(0.4,0,0.2,1) | — | **Yes** — motion curve |

**7 of 15 roles are already identical.** Only 6 produce a real pixel change, and
three of those are imperceptible.

### 1c. Pages whose appearance changes, per collision

| Collision | Pages affected | Nature of change |
|---|---|---|
| **#2** accent light | **All 24 pages extending `base.html`** — `.footer-logo span` and `.footer-links a:hover` live in the global footer (`main.css:695,706`) | Footer accent #f5a623 → #e0a040 |
| **#3** accent dark | **11 pages** using `var(--amber-dark)` directly: `core/{answer,credits,dashboard,history,wizard}`, `lawyers/{browse,dashboard,edit_profile,profile,register,review}` | Hover/active amber slightly deeper |
| **#5** sunken surface | **6 pages** via `.auth-page` (`auth/{login,register,forgot_password,reset_password}`, `lawyers/login`) and `.wizard-page` (`core/wizard`) | Page background #f2ede6 → #f0ece6 |
| **#8** deepest ink | Same **11 pages** as #3, via `var(--black)` | Imperceptible |
| **#10** secondary text | `main.css`-wide (`--text-secondary` alias + 4 direct rules) → all `base.html` pages | Imperceptible |
| **#15** easing | 12 rules in `main.css` → all `base.html` pages | Transitions gain landing's springier curve |

**Not affected by anything above:** `core/landing.html` (loads no `main.css`),
all admin pages (exempt), all email templates (exempt), the 6 error pages (no
styling of their own).

### 1d. Dead CSS found (not acting on it)

`.how-section`, `.who-section`, `.trail-answer` in `main.css` use `--cream` but
are referenced by **no template**. Three of the six `--cream` rules are dead.
Flagging only — removal is not a Phase 1 instruction.

### 1e. Font consolidation — a conflict I need you to resolve

**Instruction conflict.** Step 3 says reduce to one load *in main.css*; step 4
says do not touch any page file. But **5 of the 6 in-scope loads live in page
files**, so Phase 1 alone cannot reach 1.

| # | Load | File:line | Removable in Phase 1? |
|---|---|---|---|
| 1 | `@import` DM Sans 300–600 | `static/css/main.css:1` | **Yes** — becomes the canonical load |
| 2 | `<link>` DM Sans 300–700 | `templates/base.html:14` | No — page file (Phase 2) |
| 3 | `<link>` DM Sans 300–700 + italic | `templates/core/landing.html:11` | **See blocker F1** |
| 4 | `<link>` DM Sans 300–600 | `templates/core/for_lawyers.html:8` | No — page file (Phase 2) |
| 5 | `<link>` DM Sans + italic | `rentritz-landing/index.html:11` | Unrouted — deletion pending |
| 6 | `@import` Cormorant + DM Sans | `landing/App.jsx:16` | Unrouted — deletion pending |
| — | `@import` Inter | `static/css/admin.css:1` | **Exempt** — admin exception |

**Canonical load for `main.css`,** the union of every weight in use:
`DM Sans wght 300;400;500;600;700` + `ital 300;400;500;600`.

**Which pages change typeface: none.** Every in-scope page is already DM Sans, and
Playfair→Georgia is a no-op because Georgia is what already renders.

**One rendering change, an improvement:** `for_lawyers.html` uses
`font-weight:700` but loads only 300–600, so the browser **synthesizes faux-bold**
today. The consolidated load gives it the real 700 cut. Visible on that page.

---

## F1 — font load table (requested; nothing merged or deleted)

| # | File:line | Family / families | Weights loaded | Pages affected |
|---|---|---|---|---|
| 1 | `static/css/main.css:2` | **DM Sans** | `300;400;500;600` | All 24 `base.html` pages + `for_lawyers` |
| 2 | `templates/base.html:14` | **DM Sans** | `300;400;500;600;700` | All 24 `base.html` pages |
| 3 | `templates/core/landing.html:11` | **DM Sans** | `300;400;500;600;700` + italic `300;400;500;600` | `/` only |
| 4 | `templates/core/for_lawyers.html:8` | **DM Sans** | `300;400;500;600` | `/for-lawyers` only |
| 5 | `static/css/admin.css:1` | **Inter** | `300…900` | 18 admin pages — **exempt (F2)** |
| 6 | `templates/admin/base_admin.html:9` | **Inter** | `300…900` | 17 admin pages — **exempt (F2)** |
| 7 | `rentritz-landing/index.html:11` | **DM Sans** | `300;400;500;600;700` + italic | **None — unrouted** |
| 8 | `landing/App.jsx:16` | **Cormorant Garamond** + **DM Sans** | Cormorant ital `300…700`; DM Sans `opsz 9..40` variable | **None — unrouted** |

### The branding defect you predicted is real: three families, not one

- **DM Sans** — the public app. 6 loads, 4 different weight specs.
- **Inter** — admin. Loads 5 and 6 are a **redundant pair**: `admin.css` and
  `base_admin.html` fetch the identical URL, so admin loads Inter twice.
  Exempt under F2, but the duplication is inside the exemption.
- **Cormorant Garamond** — a serif used nowhere else, in `landing/App.jsx`.
  This is the genuine branding defect. It is unrouted, and F4 keeps the
  directory, so it cannot be fixed by deletion. **Needs a decision.**

Load 8 also requests DM Sans on the **`opsz` variable axis** while every other
load requests static `wght` — two different cuts of the same family.

**Union needed for one canonical load:** `DM Sans wght 300;400;500;600;700` +
`ital 300;400;500;600`.

**Typeface changes if consolidated: none.** Every served page is already DM Sans.
One rendering change, an improvement: `for_lawyers.html` sets `font-weight:700`
but loads only 300–600, so it renders **synthesised faux-bold** today; the union
gives it the real cut.

---

## Blocked — need your call before I write anything

**F5 — "exactly one file defines a colour" is NOT yet true, and cannot be
without inventing tokens.** `:root` is now clean — `tokens.css` is the only file
defining a colour *variable*. But `main.css` **rule bodies** still contain 68 hex
literals and 28 `rgba()` literals across ~1,800 lines. Roughly half map onto
existing tokens; the rest have **no token equivalent**:

| Group | Examples | Token exists? |
|---|---|---|
| Dark greys | `#2a2a2a` ×10, `#1a1a1a` ×6, `#0f0f0f`, `#1e1e1e`, `#141414`, `#111` | **No** |
| Neutral greys | `#e5e5e5` ×5, `#555`, `#eee`, `#ddd`, `#ccc`, `#aaa`, `#888`, `#666`, `#444`, `#f5f5f5`, `#fafafa`, `#f0f0f0`, `#d0cdc8` | **No** |
| Tints | `#fffbeb`, `#fef9c3`, `#fee2e2`, `#fde68a`, `#dcfce7`, `#854d0e` | **No** |
| White washes | `rgba(255,255,255,…)` at 12 opacities | **No** |

Tokenising these needs ~20 new tokens, which "invent no new colours" forbids.
**Three options, your call:** (a) accept literals in `main.css` rule bodies until
Phase 2 maps them page by page; (b) authorise a bounded set of new neutral tokens;
(c) leave them permanently and narrow the rule to "one file defines the token
palette", which is already true.

Worth noting: the dark greys `#2a2a2a`/`#1a1a1a`/`#0f0f0f`/`#111` in `main.css`
are admin-style values sitting in the **light** stylesheet — likely dead
dark-theme remnants. Not investigated; not touched.

**F6 — WITHDRAWN 2026-08-12. The finding was wrong.** All 7 variables *are*
defined, in the `:root` of each page's own `<style>` block, in every page that
uses them. Nothing resolves to nothing; no transition is dead; no text is the
wrong colour from this cause. **Step 1 is therefore a no-op — nothing to fix.**

How it was disproved, so this is not re-litigated:

1. Parsed every routed template for `--name:` definitions and `var(--name)`
   uses, resolving against the real cascade
   (`tokens.css` + `main.css` + `base.html` + the page's own `:root`).
   Result: **zero** undefined variables anywhere in scope.
2. The one way the definitions could still be dead is if the `<style>` block
   never rendered. Checked: `base.html` declares blocks `title`, `styles`,
   `body_class`, `content`, `scripts`, and **all 9 `<style>` blocks sit inside
   `{% block content %}`**, which `base.html` emits at line 72. They render.
   (A `<style>` in `<body>` still applies document-wide, and `:root` still
   matches `<html>`.)

Two of the 7 are genuinely unused and could be deleted as dead declarations —
`--text-dim` in `core/history.html`, `--ease-out` in `lawyers/review.html`,
plus `--dark-card-hover`/`--border-hover` in `lawyers/{dashboard,profile}.html`.
Cosmetic only. Not touched.

The original (wrong) F6 table, kept for the record:

| Variable | Templates affected |
|---|---|
| `--ease-out` | 8 — `core/{credits,dashboard,history}`, `lawyers/{browse,dashboard,edit_profile,profile,register}` |
| `--text-dim` | 8 — as above plus `lawyers/review` |
| `--dark-card-hover` | 4 — `core/{credits,dashboard,history}`, `lawyers/browse` |
| `--border-hover` | 2 — `core/dashboard`, `lawyers/browse` |
| `--body-text` | 1 — `core/answer` |
| `--border-amber` | 1 — `core/credits` |
| `--card-deep` | 1 — `core/wizard` |

Note `--ease-out` and `--text-dim` were names in the *original void brief* —
suggesting a previous partial migration was abandoned mid-flight. F7 below
shows what that abandoned migration actually did.

---

## F7 — BLOCKING. Eleven pages shadow the global tokens, so Step 5 will not reach them.

This is the real defect F6 was groping at, and it changes what Step 3 has to do.

**11 routed pages define their own `:root` inside their `<style>` block, and
those definitions override `tokens.css` for that page.** 85 declarations
conflict with the global value. Replacing a page's raw hex with `var(--token)`
is *not enough*: the `var()` will resolve against the page's own `:root`, not
against `tokens.css`. **Step 5a can repaint `tokens.css` and these 11 pages will
not move.**

Affected: `core/{answer,credits,dashboard,history,wizard}`,
`lawyers/{browse,dashboard,edit_profile,profile,register,review}`.

### The token names are inverted, not merely different

These pages were originally a dark theme. Someone converted them to light by
**flipping the values behind the names** instead of renaming:

| Token | Global (`tokens.css`) | These 11 pages | Effect |
|---|---|---|---|
| `--white` | `#ffffff` (via `--card`) | **`#1c1916`** | "white" means the darkest ink |
| `--black` | `#0e0c0a` (via `--ink-2`) | **`#f8f6f2`** | "black" means the page background |
| `--dark-card` | `#ffffff` (via `--card`) | `#ffffff` | name says dark, value is white |
| `--near-black` | `#1c1916` (via `--ink`) | **`#f0ece6`** | a near-white sunken surface |
| `--dark-card-hover` | *(page-only)* | `#f0ece6` | light hover on a light card |

So on these pages `color: var(--white)` renders **near-black text**, and
`background: var(--black)` renders a **cream page**. Any mechanical
name-based mapping in Step 3 would invert those pages.

### It also silently reverted a shipped commit

`--ease` is redefined locally as `cubic-bezier(0.4,0,0.2,1)` on **10** of the 11.
Commit `dfde279` "adopt landing easing curve" therefore has **no effect** on
those 10 pages. The easing change currently reaches only the pages with no local
`:root`. Correcting the record: that commit is narrower than it claims.

Also locally overridden: `--radius` (`14px` vs the global `12px`) on 9 pages,
`--amber`/`--amber-dark` on 11, `--text-muted` on 9, `--border` on 11.

### The decision I need

Step 3 says "replace raw hex with `var()`". On these 11 pages that is
cosmetically correct but functionally inert — it hands Step 5 a page that still
cannot be repainted. Options:

- **(a) Recommended — delete each page's local `:root` and let the page inherit
  `tokens.css`, remapping the inverted names as I go** (`var(--white)` → `var(--ink)`,
  `var(--black)` → `var(--paper)`, `var(--near-black)` → `var(--paper-2)`, and so on
  by ROLE not by name). This is what makes Step 5 actually work. It is more than
  a literal swap, so it needs your say-so. Visible change on those 11 pages:
  radius 14px→12px, easing to the landing curve, amber to `#c8820a`.
- **(b) Keep the local `:root` blocks and repaint each of them by hand with the
  R1 values in Step 5.** Preserves per-page values exactly, but keeps 11 extra
  colour sources forever and contradicts "one file defines colour".
- **(c) Literals only, as written.** Step 5 then leaves 11 of 26 pages amber
  while the rest go crimson — the precise half-migrated state Step 3's ordering
  exists to prevent.

**DECIDED: option (a).** Delete each page's local `:root`; remap call sites by
ROLE. The table below is the contract — apply it mechanically, do not re-derive.

### F7 role map — the ONLY mapping Step 3 may use on those 11 pages

Never map by name. `--white` and `--black` mean the opposite of what they say.

| Page-local declaration | Value | Rewrite call sites to | Δ |
|---|---|---|---|
| `--white` | `#1c1916` | `var(--ink)` | exact |
| `--black` | `#f8f6f2` | `var(--paper)` | exact |
| `--near-black` | `#f0ece6` | `var(--paper-2)` | exact |
| `--card` | `#ffffff` | `var(--card)` | exact |
| `--dark-card` | `#ffffff` | `var(--card)` | exact |
| `--dark-card-hover` | `#f0ece6` | `var(--paper-2)` | exact |
| `--card-deep` | `#f0ece6` | `var(--paper-2)` | exact |
| `--hero-bg` | `#f0ece6` | `var(--paper-2)` | exact |
| `--border` | `rgba(58,53,48,0.12)` | `var(--rule)` | exact |
| `--text-dim` | `#9a8f82` | `var(--dim)` | exact |
| `--text-muted` | `#6b6157` *(credits)* | `var(--muted)` | exact |
| `--text-muted` | `#6b6259` *(8 pages)* | `var(--muted)` | ≈ **[C10]** imperceptible |
| `--amber` | `#c8820a` | `var(--amber)` | exact |
| `--amber` | `#f59e0b` *(credits)* | `var(--amber)` | **[C1]** visible |
| `--amber-dark` | `#b8720a` | `var(--amber-2)` | **[C3]** slightly deeper |
| `--amber-dark` | `#d97706` *(credits)* | `var(--amber-2)` | **[C3]** visible |
| `--ease-out` | `cubic-bezier(.22,1,.36,1)` | `var(--ease)` | exact |
| `--ease` | `cubic-bezier(.4,0,.2,1)` | `var(--ease)` | **[C15]** visible |
| `--radius` | `14px` | `var(--radius)` = `12px` | visible, approved under (a) |

**Note the trap at `--text-muted`.** `main.css:40` aliases it to `var(--dim)`
(#9a8f82, tertiary), but all 11 pages use it as *secondary* (#6b62xx). Deleting
the local declaration and letting it inherit would therefore **wash the text out
by one step**. Call sites must be rewritten to `var(--muted)` explicitly —
inheritance is not safe for this one name.

### F7 residue — 5 values with no token. Do NOT invent one.

These stay as page-local declarations, renamed so they no longer shadow a global
token, and are carried into the Step 4 leftover report as candidate new tokens:

| Page-local | Value | Page(s) | Why it does not map |
|---|---|---|---|
| `--muted` | `rgba(58,53,48,0.5)` | answer, wizard | translucent; global `--muted` is opaque `#6b6157`. **Shadows a real token — must be renamed.** |
| `--body-text` | `rgba(28,25,22,0.87)` | answer | 87% ink; no token |
| `--subtle` | `rgba(28,25,22,0.7)` | wizard | 70% ink; no token |
| `--border-hover` | `rgba(200,130,10,0.35)` | 4 pages | nearest is `--amber-border` at **0.25** |
| `--border-amber` | `rgba(245,158,11,0.35)` | credits | different hue *and* alpha |

---

## F8 — BLOCKING for Step 5. 92% of the leftovers are alpha variants of tokens.

Surfaced while doing page 1. The "leave it and log" rule is producing a log that
is not a pile of stray colours — it is **the same tokens at partial opacity**.

Across all 26 in-scope pages plus `main.css`: **352 `rgba()` literals, 327 of
them (92%) are an existing token's RGB at some alpha.** Only 25 are unrelated
colours.

| Underlying colour | Occurrences |
|---|---|
| `rgb(245,158,11)` — the **old admin amber**, not `--amber` | **89** |
| `rgb(58,53,48)` — `--rule`/`--deep-grey` | 63 |
| `rgb(255,255,255)` — white/`--card` | 56 |
| `rgb(248,246,242)` — `--paper` | 40 |
| `rgb(200,130,10)` — `--amber` | 34 |
| black, `--ink`, `--dark`, `--ink-2`, `--amber-soft`, `--dim` | 45 |
| genuinely unrelated (greens/blues — status colours) | 25 |

**Why this decides Step 5.** A hex swap in `tokens.css` cannot reach any of
these. Repaint the palette and the solid fills go crimson while **327
translucent borders, shadows, hovers, glows and washes stay amber**. That is the
half-migrated state the whole step ordering exists to prevent — and it is
2.4× larger than the 134 solid literals I have logged so far.

The 89 `rgb(245,158,11)` are worse than stale: that is the *admin* amber leaking
into non-admin pages. They do not match `--amber` (`#c8820a`) today, so those
pages are already off-palette before any crimson lands.

**This cannot be fixed by "replace with `var()`"** — you cannot vary the alpha of
a hex token. It needs a mechanism, and every option is a structural change I
will not make unilaterally:

- **(a) Channel tokens.** Add `--brand-rgb: 214,38,58` etc. alongside each hex,
  then `rgba(var(--brand-rgb), .35)`. Widest browser support, no new *colours* —
  the same values in a second notation. Costs one extra token per colour.
- **(b) `color-mix()`.** `color-mix(in srgb, var(--brand) 35%, transparent)`.
  No new tokens at all. Baseline in all current browsers; fails on Safari < 16.2.
- **(c) Relative colour.** `rgb(from var(--brand) r g b / .35)`. Cleanest syntax,
  narrowest support (no Firefox before 128).
- **(d) Accept it.** 327 literals stay on the old palette permanently.

Recommend **(a)** — it is the only one with no compatibility question, and adding
a second notation for a colour already in the list is not inventing a colour.

**Do not start Step 3 pages 2-26 until this is settled**, because the answer
changes what "tokenise this page" means for roughly 12 literals per page.

---

## F9 — Step 5a as written deletes 22 tokens that are in use.

"Replace every value in `tokens.css` with the R1 palette" is not a substitution:
`tokens.css` defines **31** tokens, R1 names **14**. **22 have no R1 counterpart**
and every one of them is referenced by live CSS.

| Group | Tokens | R1 answer? |
|---|---|---|
| **Dark surfaces** | `--dark` `#0a0807`, `--dark-mid` | **none — see below** |
| Accent ramp | `--amber`, `--amber-soft`, `--amber-2`, `--amber-glow`, `--amber-border` | `--brand`/`--brand-deep`/`--brand-soft` cover 3 of 5 |
| Rules | `--rule-soft`, `--border-strong` | only `--rule` given |
| Neutrals | `--light-sand`, `--deep-grey` | none |
| Status | `--error-bg/-bd/-text`, `--success-bg/-bd/-text` | only flat `--error` and `--action` |
| Shadows | `--shadow`, `-sm`, `-md`, `-lg`, `-amber` | none — brief forbids inventing a shadow |

**The sharp one is `--dark`.** Landing is a two-tone page: cream sections
alternating with near-black `#0a0807` sections, and it is the reference page.
R1 is "light mode only" and offers no dark surface, so as written Step 5a leaves
landing's dark sections with no colour. Its darkest value is `--ink-2 #0D0709`,
a *text* colour. Using it as a section background is a role change, not a
value swap.

Three of these need your decision before 5a can run at all: what `--dark` and
`--dark-mid` become; whether the shadows keep their current rgba (they are
`rgba(28,25,22,…)` — an `--ink` alpha, so F8's answer covers them); and whether
the 6 status tokens collapse into flat `--error`/`--action` or keep bg/border/text
triplets. Not acting.

**DECIDED for `--dark`:** keep `#0a0807` and `--dark-mid` through the swap
unchanged, as a named exception alongside `admin.css`. Landing keeps its
two-tone structure; the crimson lands on the accents.

---

## F10 — answers your Step 4 question about the dark greys, early.

You asked whether `#2a2a2a / #1a1a1a / #0f0f0f / #111` in `main.css` are
reachable from any template. **Mostly no — but the answer came with a surprise.**

### `main.css`: 18 selectors carry a dark grey, 10 distinct classes. 9 are dead.

| Reachable from a routed template | Not referenced by any routed template |
|---|---|
| `.nav-admin` — `base.html:47`, the dark admin strip shown when an admin browses the public app | `.admin-body`, `.admin-form-card`, `.admin-login-card`, `.admin-login-page`, `.admin-table-wrap`, `.stat-card`, `.tree-canvas`, `.tree-node`, `.tree-option` |

The 9 are admin/tree-builder classes that live in **admin** templates, and those
load `admin.css`, not `main.css`. So these are duplicated dead rules — a dark
theme's remnants sitting in the light stylesheet, confirming the earlier hunch.
**Recommend deleting the 9, keeping `.nav-admin`.** Not acted on; it is removal,
not presentation, and Step 4 says report only.

### The surprise: two in-scope pages are genuinely dark, today.

`core/terms.html:7` and `core/privacy.html:7` set `body{background:#0a0a0a}` in
their **own** `<style>`, overriding `main.css`'s `var(--bg)`. Verified live:
`/terms` computes `bodyBg rgb(10,10,10)`, `bodyColor rgb(229,229,229)`.

Pre-existing — neither file has been touched in this migration. But it means
**"light mode only" is not the current state**, and R1 has no dark surface. Two
of your 26 pages need a decision that Step 5 as written does not cover:

- fold them into the light palette (a visible redesign of both pages), or
- treat them like landing's dark sections and keep them dark on `--dark`.

Not acting. Flagging under Blocked.

**F1 — CLOSED by Step 2, and my earlier recommendation was unnecessary.** I had
said landing must keep its own font link because it loads no `main.css`. It does
not need one: landing already `<link>`s `tokens.css` directly (line 12), so
putting the single `@import` in `tokens.css` reaches landing, `base.html`'s 24
children (via `main.css`), and `for_lawyers.html` alike. **One load, genuinely.**
Verified live through Flask, not by inspection:

| Route | `<link>` to fonts.googleapis in head | DM Sans active | Faces downloaded |
|---|---|---|---|
| `/` | none | yes | 300/400/500/600 + italics |
| `/for-lawyers` | none | yes | **700 real cut present** |
| `/terms` | none | yes | 400/600 |

`/for-lawyers` previously loaded only 300–600 while setting `font-weight:700`,
so its bold was browser-synthesised. `document.fonts.check('700 16px "DM Sans"')`
now returns **true** on that route. That is the one intended visible change.

**F2 — the exempt-admin amber.** B2 says all collisions resolve to landing's
`#c8820a`, but admin is now a permanent exception with its own `#f59e0b`. Does
the amber unification reach into `admin.css` or not? For information: `#c8820a`
on admin's `#111111` gives a **5.98:1** contrast ratio versus `#f59e0b`'s
**8.79:1** — both pass WCAG AA for body text, so either is defensible.
**Recommend: leave `admin.css` alone**, consistent with the exemption.

**F3 — motion curve, #15.** Adopting landing's `cubic-bezier(0.22,1,0.36,1)`
changes every transition on all 24 `base.html` pages. It is a genuine collision
and the rule says landing wins, but it is the single most broadly visible change
in Phase 1 and is easy to miss in review. Confirm you want it.

**F4 — `rentritz-landing/` deletion.** Verified unreachable (see
`DESIGN_AUDIT.md` §B5): not rendered, not extended, not included, not in Flask's
static path, and the repo has no deploy config at all. Caveat: deployment may be
configured outside this repo. Say the word and it goes in its own commit.

---

## Phase 2 — pages, in order (unstarted)

- [ ] 1. `templates/core/landing.html` — `/` — 58 hex, own `:root`
- [ ] 2. `templates/core/dashboard.html` — `/dashboard` — 25 hex
- [ ] 3. `templates/core/wizard.html` — `/consult/<slug>` — 8 hex
- [ ] 4. `templates/core/answer.html` — `/answer/<id>` — 17 hex
- [ ] 5. `templates/lawyers/browse.html` — `/lawyers/` — 16 hex
- [ ] 6. `templates/lawyers/profile.html` — `/lawyers/<id>` — 22 hex
- [ ] 7. `templates/auth/login.html` + `register.html` — 5 hex
- [ ] 8. `templates/core/credits.html` — 15 hex
- [ ] 9. `templates/core/history.html` — 12 hex
- [ ] 10. `templates/core/for_lawyers.html` — 43 hex, own font link
- [ ] 11. `templates/lawyers/dashboard.html` — 18 hex
- [ ] 12. `templates/lawyers/edit_profile.html` — 10 hex
- [ ] 13. `templates/lawyers/register.html` + `login.html` — 14 hex
- [ ] 14. `templates/lawyers/review.html` — 10 hex
- [ ] 15. `templates/auth/forgot_password.html` + `reset_password.html` — 2 hex
- [ ] 16. `templates/core/terms.html` + `privacy.html` — 37 hex
- [ ] 17. `templates/errors/*.html` ×6 — already clean, verify only

Pause for review after every 3 ticked pages.

### Per-page log (Step 3)

| # | Page | Commit | Replaced | Left + logged |
|---|---|---|---|---|
| 1 | `templates/core/landing.html` | `a0f77f1` | 25 | 134 |
| 2 | `templates/core/dashboard.html` | `f4f764c` | 26 var + 26 lit | 13 |
| 3 | `templates/core/wizard.html` | `4e46bb0` | 17 var + 7 lit | 1 |
| — | `core/dashboard.html` onboarding modal | `885f979` | 7 (D2, to light) | 1 |
| 4 | `templates/core/answer.html` | `17c087d` | 14 var + 24 lit | 13 |
| 5 | `templates/lawyers/browse.html` | `c743d92` | 38 var + 19 lit | 4 |
| 6 | `templates/lawyers/profile.html` | `76331b4` | 59 var + 11 lit | 8 |
| — | `lawyers/profile.html` rating script | `d8af096` | 9 (F11 closed) | 0 |
| 7 | `auth/login.html` + `register.html` | `6af6a04` | 7 lit | **0 — fully clean** |
| 8 | `templates/core/credits.html` | `dd97a87` | 41 var + 12 lit | 5 |
| 9 | `templates/core/history.html` | `f81319f` | 18 var + 10 lit | 6 |
| 10–26 | — | — | — | not started |

**Next up:** 10 `core/for_lawyers`, 11 `lawyers/dashboard`, 12 `lawyers/edit_profile`.

### F12 — the status family has no channel tokens. BLOCKING for Step 5.

D7 fixes the status *values*. It does not solve their *alpha variants*, which is
the F8 problem again, unsolved for this family:

| Wash | Count | Where | Signal |
|---|---|---|---|
| `rgba(74,222,128,a)` | 5 | `history` pills, `profile` | success |
| `rgba(16,185,129,a)` | 2 | `profile`, `browse` | success / verified |
| `rgba(96,165,250,a)` | 2 | `profile` | info |

Solid values are routed to `--success-text` / `--error-text` and will follow D7.
**The washes cannot**, because you cannot vary the alpha of a hex.

Consequence if left: after Step 5 status *text* migrates while the pill
*backgrounds* behind it stay the old light green/blue. I have not invented
`--success-rgb` etc. to fix it — that is a token decision, so it is in the
orphan report.

**Next up:** 7 `auth/login` + `register`, 8 `core/credits`, 9 `core/history`.

### F11 — colour literals inside `<script>` blocks. Reported, not acted on.

`lawyers/profile.html` sets star-rating colours from JS
(`l.style.color = i<=idx ? '#f59e0b' : '#555'`, lines 523/528/533, plus one
`#f87171`). Those are string literals in a script, not CSS rule bodies, so
editing them is a code change and the presentation-only rule stops me.

**After Step 5 the stars stay amber while the page goes crimson.** Logged in
`DESIGN_EYEBALL.md` so it is not mistaken for a bug. One-token fix per line
(`'var(--amber)'` works on inline styles) once approved.

Audited all six done pages for this hazard: only `landing.html` else has colour
in a script, and it was already `var(--ink)`/`var(--ease)` before my commit.

**Do remap `var()` NAMES inside scripts** — `profile` and `dashboard` both emit
inline styles referencing `--text-dim`, which would break when the local `:root`
is deleted. Renaming a token reference is not a logic change.

### Two traps hit while doing pages 4–6

1. **Do not put a hex in the explanatory comment you insert.** On `browse.html`
   the literal pass rewrote my own comment, turning "--white was #1c1916" into
   "--white was var(--ink)". Describe the inversion in prose instead.
2. **Strip `&#nnnn;` before inventorying literals.** `&#8594;` (→) and
   `&#128196;` (📄) look exactly like hex colours and will pollute the count.

**F8 resolved most of the F7 residue.** With channel tokens available,
`rgba(58,53,48,.5)`, `rgba(28,25,22,.87)`, `rgba(28,25,22,.7)` and
`rgba(200,130,10,.35)` all became expressible, so they are no longer leftovers.
Only `--border-amber` (`rgba(245,158,11,.35)`, credits) still needs the [C1] hue
call, and it gets the same treatment as every other `#f59e0b` wash.

**Enabling commit:** `6e206fc` `refactor(tokens)` — every colour now derives from
an `R,G,B` channel triplet, so Step 5 edits triplets only. **Do not hand-edit the
derived hex tokens.** A nested CSS comment blanked the whole file once during
that change; the warning is in `tokens.css`.

**Verification available per page.** Pages 2+ are behind a login. I will not
enter credentials, so those get mechanical verification only — every remaining
token name resolves globally, `<style>` braces and comments balance, and no
token-alpha literal is left un-channelled. **Visual confirmation of every
authenticated page is deferred to Step 7 and needs a logged-in session from you.**
Public routes verified live so far: `/`, `/terms`, `/for-lawyers`.

### Decisions settled 2026-08-13 — do not re-litigate

| # | Decision |
|---|---|
| **D1** | `terms.html` + `privacy.html` `body{background:#0a0a0a}` is **drift, not design**. Convert both to R1 light: `--paper` background, `--ink` text. They stay in the normal 26 (page 16). Large visible change → **top of the eyeball list**. |
| **D2** | Dashboard onboarding modal → **light**. `--card` panel on a dimmed backdrop. **No dark overlay token.** Done in `885f979`. |
| **D3** | The 9 dead dark-grey classes **stay**. Unreachable, so they render nothing, and deleting is removal not presentation. Logged under *post-merge cleanup* below. `.nav-admin` **is** reachable → tokenise it normally. |
| **D4** | **Step 7 auth is settled.** Never ask for or accept credentials. I screenshot public routes only: `/`, `/for-lawyers`, `/terms`, `/privacy`, 4 auth, 6 error. Every authenticated page gets a written checklist instead — `DESIGN_EYEBALL.md`, updated **after every page**, not at the end. |

### D5 — THE DARK SURFACE RULE. Apply this, do not decide case by case.

> **A dark surface is allowed ONLY when it is a hero, or a full-bleed section
> behind a headline. Everywhere else is light.**

| Surface | Hero? | Ruling |
|---|---|---|
| `landing.html` dark sections | **yes** — hero / full-bleed behind headlines | **stays dark** |
| `answer.html` `.ans-hero` | **yes** — hero | **stays dark** |
| `terms.html` / `privacy.html` `body` | **no** — a full page of reading text | **convert to light**, page 16 |
| `dashboard.html` onboarding modal | **no** — a panel | converted, `885f979` |

Every remaining dark surface is decided against this rule. Open item still to
be judged: `answer.html` `.btn-rera` (black CTA, hovers `#1a1a1a`) — a button,
not a hero, but also not a *surface*; treated as a high-contrast control and
left, flag if you disagree.

**The intended consequence, stated plainly so nobody "fixes" it later:**
after Step 5 the two heroes stay near-black while the rest of the app is warm
white. **That is deliberate two-tone, not drift.**

### D6 — the five shadows are not orphans

They are `--ink` at various opacities. R1 moves ink `#1c1916` → `#1A1214`, so
each shadow is **recomputed from the new ink triplet at its existing opacity**.
Structure, geometry and alpha unchanged; nothing invented.

Already mechanical: `6e206fc` routed all five through `rgba(var(--ink-rgb),a)`,
so Step 5 updates `--ink-rgb` and every shadow follows on its own. **No action
needed at Step 5 beyond editing the triplet.**

### D7 — status colours are signals, never brand

| Signal | Becomes | Rule |
|---|---|---|
| success | `--action` `#1F6B45` | |
| error **and warning** | `--error` `#B45309` | |
| info | existing blue, **unchanged** | |

> **Status colours must NEVER become crimson.** Red is the brand now; a red
> error would be indistinguishable from a brand element.

Pages currently carrying raw status literals to be repointed at Step 5:
`#4ade80` / `rgba(74,222,128,a)` and `#16a34a` (success), `#f87171` (error —
already routed to `--error-text` in `profile.html`, `d8af096`), `#10b981`
(success/verified), `#60a5fa` / `rgba(96,165,250,a)` (info — leave).

### F13 — BLOCKING and the biggest finding for Step 5: the accent ramp is mostly TEXT

R1 is explicit: `--brand` is **FILLS ONLY**, never text on light; `--brand-deep`
is the token for red text and links. But the accent this replaces is used as
text more than as fill:

| Token | `color:` | fills (`background`) | borders / other |
|---|---|---|---|
| `--amber` `#c8820a` | **107** | 62 | 32 |
| `--amber-soft` `#e0a040` | **17** | 4 | 2 |
| `--amber-2` `#a86a08` | 5 | 12 | 2 |

**A 1:1 swap of `--amber` → `--brand` would put `#D6263A` on light backgrounds
as text in 107 places**, breaking the rule you wrote, at the very ratio you
flagged as thin (~4.9:1).

The ramp cannot map token-to-token. It has to split **by property**:
`color:` → `--brand-deep`, fills → `--brand`. That is ~124 call sites across
the app and it cannot be done by find-and-replace on the token name — every
site needs its property inspected, exactly like the F7 role map.

**Not started. Needs your ruling before Step 5a.**

### Orphan report — the tokens still needing a decision

Everything else in F9 is now settled: shadows D6, status values D7, `--dark` /
`--dark-mid` D5. These remain:

| Token | Value | Styles | R1 problem |
|---|---|---|---|
| `--amber` | `#c8820a` | accent, 201 sites | see **F13** — splits by property |
| `--amber-soft` | `#e0a040` | gradient partner to `--amber`; 17 text sites | R1's `--brand-soft` `#F5D5D9` is a pale tint, **not** a gradient partner. No equivalent. |
| `--amber-2` | `#a86a08` | hover / deeper accent | maps to `--brand-deep` cleanly |
| `--amber-glow` | `rgba(amber,.12)` | washes | derives from the brand channel, mechanical |
| `--amber-border` | `rgba(amber,.25)` | accent borders | derives from the brand channel, mechanical |
| `--rule-soft` | `rgba(58,53,48,.06)` | faint dividers | R1's `--rule` is `rgba(26,18,20,.12)` — **ink**-based, not deep-grey. Rebase? |
| `--border-strong` | `rgba(58,53,48,.22)` | emphasised dividers | same rebase question |
| `--light-sand` | `#ebe4d8` | warm neutral fill | no R1 counterpart |
| `--deep-grey` | `#3a3530` | the base of every rule/border | no R1 counterpart, and R1 implies rules move to ink |
| status channels | — | 9 washes | **F12** — no `--success-rgb` etc., so pill backgrounds cannot follow D7 |

Page-level literals with no token, for the same decision:
`#000` / `#fff` button labels (56 sites), `rgba(0,0,0,a)` shadows and scrims
(~20), `#0d0d0d` + `#1a1a1a` (answer hero and CTA, kept dark under D5),
`#d68b0c` (landing's amber button hover), `#2a2018` (for_lawyers).

### STEP 5 PROPERTY MAP — F13 resolved. Mechanical, not per-site.

**This was missing from the original Step 5 plan.** The accent ramp cannot map
token-to-token, because `--amber` is used as text (107) more than as fill (62).
The **CSS property name decides it**, with no judgement per site:

| Property | Becomes |
|---|---|
| `color:` | `--brand-deep` |
| `background`, `background-color`, `fill`, gradient stops | `--brand` |
| `border-color`, `border` shorthand, `outline` | `--brand` |
| `box-shadow` | `--brand` |
| SVG `stroke` on an icon beside text | `--brand-deep` |

**Do NOT perform 124 manual inspections.** Write a script for this pass.

**Then exactly one manual exception review:** `color: var(--amber)` occurring
inside a **dark-surface** selector — the landing hero and `answer.html`'s
`.ans-hero`. Deep crimson on near-black is too dark; those sites need `--brand`
or lighter. Small set, not 124.

**Contrast context (see `DESIGN_AUDIT.md`):** `#c8820a` on paper is **2.92:1**
and already fails AA today. `#D6263A` is 4.87:1, `#9B1B2B` is 7.90:1. Routing
text to `--brand-deep` takes those 107 sites from failing to ~8:1. Crimson is a
fix here, not a risk.

### Orphans — RESOLVED. No open token decisions remain.

| Token / literal | Resolution |
|---|---|
| `--amber` | splits by property, see the map above |
| `--amber-soft` *(17 text sites)* | `--brand-deep` |
| `--amber-soft` *(gradient role)* | **NEW `--brand-light` `#E8546A`** — an **invented value**, the only one in this migration. **Fill and gradient ONLY, never text.** Contrast-check in Step 6 if white text ever sits on it. |
| `--amber-2` | `--brand-deep` |
| `--amber-glow`, `--amber-border` | derive from the brand channel, mechanical |
| `--rule-soft` | `rgba(var(--ink-rgb), .06)` |
| `--border-strong` | `rgba(var(--ink-rgb), .22)` |
| `--deep-grey` | **dissolves** — rebase every user onto the ink channel |
| `--light-sand` `#ebe4d8` | `--paper-2` — same role, warm sunken fill |
| `#d68b0c` landing button hover | `--brand-deep` (hover on a fill) |
| `rgba(0,0,0,a)` shadows and scrims | `rgba(var(--ink-rgb), a)`, **same opacities**, consistent with D6 |
| `#000` / `#fff` labels, 56 sites | **leave as literals.** Achromatic, no token needed. **Permanent named exception** — logged here so no future pass "fixes" them. |
| `#2a2018` in `for_lawyers` | decide by role at page 10 |
| status washes | closed by F12, `b12a409` |

**Note on `--deep-grey` dissolving:** every page done so far writes
`rgba(var(--deep-grey-rgb), a)` for rules and borders. At Step 5 that becomes a
single find-and-replace to `--ink-rgb` across the tree, because the channel name
is uniform. That uniformity is the whole reason the F8 refactor was worth doing.

### Post-merge cleanup — one chore, AFTER the PR merges, never during

Dead CSS in `main.css`, unreachable from any routed template (see F10). Removal,
not presentation, so it does not belong in this PR:

`.admin-body`, `.admin-form-card`, `.admin-login-card`, `.admin-login-page`,
`.admin-table-wrap`, `.stat-card`, `.tree-canvas`, `.tree-node`, `.tree-option`
— 18 selectors carrying dark greys. **Keep `.nav-admin`**, it is live at
`base.html:47`.

### The guard — run after EVERY page commit

```
node scripts/check-design.mjs
```

Added in `356cf22` because the nested-comment failure was silent — no console
error, no build error, no test failure. Checks nested comments, unterminated
comments, real delimiter counts, brace balance, stray top-level declarations,
the 12 channel tokens, and finally **fetches `/static/css/tokens.css` over HTTP**
to assert `--paper-rgb` is in what the browser actually receives. Needs the app
running; `--skip-http` for static only. Every check was proven to fire against a
deliberately broken file.

**Standing per-page recipe** (pages 4–26), so this is not re-derived:
1. Inventory the local `:root` and every `var()` and literal. Strip `&#nnnn;`
   HTML entities first — `&#8594;` and `&#128196;` look like hex colours and are not.
2. Delete the local `:root`; remap call sites via the F7 table, **by role**.
3. Literals: exact → token; token-at-alpha → `rgba(var(--x-rgb),a)`;
   `#f59e0b`/`rgba(245,158,11,a)` → `--amber`/`--amber-rgb` under [C1].
4. Leave and log anything else — status greens/reds, pure black/white text,
   dark-panel greys.
5. Check braces and comments balance per `<style>` block; confirm every
   remaining token name is globally defined.
6. One commit per page. Update this table AND DESIGN_EYEBALL.md.
7. Run node scripts/check-design.mjs after the commit.

**Page 1 detail — `core/landing.html`.** No local `:root`; inherits `tokens.css`.
Replaced, all value-identical: `#f8f6f2`→`var(--paper)` ×8, `#1c1916`→`var(--ink)` ×6,
`#0a0807`→`var(--dark)` ×5, `#c8820a`→`var(--amber)` ×2, `#e0a040`→`var(--amber-soft)` ×2,
`#0e0c0a`→`var(--ink-2)` ×1, `rgba(200,130,10,0.25)`→`var(--amber-border)` ×1.

Left in place: 134. Grouped by what they style — `color` 52, `background` 33,
`box-shadow` 15, gradient stops 14, borders 13, `background-image` 3, plus
**4 `#fff` on lines 103–104 that are `mask` channels, not colours — never
tokenise those.** `#fff`/`#000` are text-on-dark/amber and have no text token
(`--card` is a surface); `#d68b0c` is the amber button hover, no token.

Verified through Flask: all 7 tokens resolve to the original literals and
`.on-dark .section-h` still computes `rgb(248,246,242)`. Page unchanged.

> Method note for whoever resumes: my first contrast probe reported 215
> "failures" on landing. It was wrong — it ignored `background-image`/gradients
> and did not composite alpha, so it read the dark hero as white-on-paper. This
> is the same false alarm that halted the previous session. For a
> value-preserving swap, verify that each `var()` **resolves to the original
> literal**; do not eyeball contrast heuristics.

---

## Phase 3 — check script (unstarted)

`scripts/check-design.mjs`, wired to `npm run check:design`. Fails on:
- any hex in `templates/` **excluding `templates/email/`**
- any `font-family` outside `static/css/main.css`
- any `prefers-color-scheme` block

Admin exemption must be encoded explicitly, or the script will fail on
`admin.css` and the 18 admin templates.

## Phase 4 — pull request, no auto-deploy (unstarted)
