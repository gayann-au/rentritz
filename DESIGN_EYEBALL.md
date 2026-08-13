# DESIGN_EYEBALL.md

**The Step 7 review list.** Built as each page is tokenised, while the changes
are fresh — not written up at the end.

Split by who can check what:

- **I screenshot** the public routes: `/`, `/for-lawyers`, `/terms`, `/privacy`,
  the 4 auth pages, the 6 error pages.
- **You check** every authenticated page. I never log in and never take
  credentials, so for those pages this file is the deliverable: what changed,
  and exactly what to look for.

Nothing here is a redesign. Unless a row says otherwise, the change is
value-identical and the page should look **exactly** as it did.

---

## Priority — the three large visible changes

Look at these first. They are the only intentional departures so far.

| # | Page | Route | What changed | What to look for |
|---|---|---|---|---|
| P1 | `core/terms.html` | `/terms` | **Was a near-black page.** `body{background:#0a0a0a}` → light R1 surfaces, `--paper` background, `--ink` text | Whole page flips from near-black to warm white. Confirm the legal text is comfortably readable, headings still separate from body, and no element kept a dark background it now sits alone on. **Not yet done — page 16.** |
| P2 | `core/privacy.html` | `/privacy` | Same as P1 | Same as P1. Should end up visually identical in treatment to `/terms`. **Not yet done — page 16.** |
| P3 | `core/dashboard.html` onboarding modal | `/dashboard`, new users only | **Was a dark panel.** `#111111` → `var(--card)`; backdrop `rgba(0,0,0,0.92)` → `rgba(var(--ink-rgb),0.55)`; text `#ffffff`/`#888888`/`#555555` → `--ink`/`--muted`/`--dim` | Modal is now a white card on a dimmed page. **Judge the scrim specifically** — 55% ink is my number, not a palette value. Too light and the modal stops feeling modal; too heavy and it reads as a takeover. Also confirm the three text levels still rank: heading darkest, then secondary, then the faintest label. Trigger it with a new account. |

---

## Authenticated pages — you check these

| Page | Route | Changed | What to look for |
|---|---|---|---|
| `core/dashboard.html` | `/dashboard` | `:root` removed, 26 vars + 26 literals remapped | Amber accents shift from `#f59e0b` to `#c8820a` — slightly deeper, less yellow **[C1]**. Hover amber deeper **[C3]**. Card corners 14px → **12px**, subtle; check cards and buttons. Transitions pick up the springier landing easing **[C15]**. Secondary text `#6b6259` → `#6b6157`, should be imperceptible. Status pills (green/red) deliberately unchanged. |
| `core/wizard.html` | `/consult/<slug>` | `:root` removed, 17 vars + 7 literals remapped | Same amber shift **[C1]** and deeper hover **[C3]**. The two `#f59e0b` washes behind step indicators become `#c8820a`. Submit button label stays white on amber. Page background unchanged. |

---

## Public pages — I screenshot these

| Page | Route | Changed | Status |
|---|---|---|---|
| `core/landing.html` | `/` | 25 literals → tokens, all value-identical | Verified live: every token resolves to its original value, `.on-dark .section-h` still computes `rgb(248,246,242)`. **Expect zero visible change.** Still to do at Step 7: check the Burj Khalifa hero against the new red once Step 5 lands. |
| `core/for_lawyers.html` | `/for-lawyers` | Font load only | Bold text is now the **real** DM Sans 700 cut instead of browser-synthesised faux-bold. Look at headings and any bold run — they should look cleaner, slightly narrower. |
| `core/terms.html` | `/terms` | See **P1** | Not yet done |
| `core/privacy.html` | `/privacy` | See **P2** | Not yet done |
| 4 auth pages | `/login` etc. | — | Not yet done |
| 6 error pages | — | — | Not yet done |

---

## Applies to every page

- **The font merge.** Four DM Sans loads became one. Every routed page should
  still render DM Sans; if any page falls back to a system sans, that is a
  regression. Verified live on `/`, `/terms`, `/for-lawyers`.
- **No dark mode.** No `prefers-color-scheme` block was added anywhere.
- **Admin is exempt** and stays dark on Inter. `/admin/*` is out of scope.

## Not to be alarmed by

- **Status colours are deliberately untouched** — greens (`#4ade80`), reds
  (`#f87171`) and their washes have no token and were left as literals by the
  "leave it and log" rule. They will still look un-migrated after Step 5.
- **Button label text** stays `#fff` / `#000000`. There is no white or black
  *text* token; `--card` is a surface. Logged, not an oversight.
