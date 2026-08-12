# DESIGN_MIGRATION.md

Working checklist. **This file is the memory between sessions.**

**Decision:** consolidate the existing design. Invent nothing.
**Reference page:** `templates/core/landing.html` — all collisions resolve to its
current values.

**Status: Phase 1 analysis done. No file has been edited. Awaiting sign-off on
the tables below before any write.**

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

## Blocked — need your call before I write anything

**F1 — landing's font link.** Landing loads no `main.css`, so deleting its
`<link>` would leave it with no webfont. Reaching literally one load requires
landing to load `main.css`, which risks bleeding main.css rules into a page whose
whole value is being self-contained — and it would change the reference page.
**Recommend: leave landing's link, accept 2 loads in the served app** (one for
the public app, one for landing) and treat "1 load" as satisfied for the
`main.css` system. Confirm.

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

### Per-page log

| # | Page | Commit | What changed |
|---|---|---|---|
| — | — | — | *(none yet)* |

---

## Phase 3 — check script (unstarted)

`scripts/check-design.mjs`, wired to `npm run check:design`. Fails on:
- any hex in `templates/` **excluding `templates/email/`**
- any `font-family` outside `static/css/main.css`
- any `prefers-color-scheme` block

Admin exemption must be encoded explicitly, or the script will fail on
`admin.css` and the 18 admin templates.

## Phase 4 — pull request, no auto-deploy (unstarted)
