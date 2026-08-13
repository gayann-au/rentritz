# DESIGN_EYEBALL.md

> # ⚠️ HARD-RELOAD EVERY PAGE BEFORE YOU JUDGE IT
>
> **Ctrl+Shift+R (or Cmd+Shift+R). Every page, every time.**
>
> The browser has served a stale stylesheet **twice** during this migration
> while the file on disk and the file on the server were both correct. A soft
> reload is not enough — CSS is cached aggressively and you will be looking at
> the old palette.
>
> ## AND START THE SERVER WITH `--dev`
>
> ```
> python run.py --dev
> ```
>
> **Step 7 MUST run against a freshly restarted server.** A hard browser reload
> does **NOT** defeat Jinja's template cache — that staleness is server-side.
> Without `--dev`, Flask compiles each template once and serves that copy for
> the life of the process, so template edits are invisible no matter what the
> browser does. Startup prints `DEV MODE: template auto-reload ON`; if you do
> not see that line, stop and restart.
>
> **Every visual check made before Step 7 is superseded** and none is cited as
> evidence anywhere. This review is the only one that counts.
>
> **A stale page makes your review worthless**, and worse, it produces
> confident wrong conclusions: you would report bugs that do not exist and miss
> ones that do. If anything looks unchanged when this file says it changed,
> hard-reload before reporting it.

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
### ⚠️ P1/P2 are the largest visual change in the project — read before reviewing them

Dark-to-light breaks things a colour swap does not. Specifically checked when
those pages are done:

- **Every `color:#fff` / `color:white` must become `--ink`.** Miss one and that
  text is invisible on the new light background. This is the failure mode — not
  "looks a bit off", but *gone*.
- **Borders and dividers were built to show against near-black.** On light they
  either vanish or read far too heavy. Each one checked individually.
- Own commit, first item here.

| P1 | `core/terms.html` | `/terms` | **DONE — was a near-black page.** `body{background:#0a0a0a}` → light R1 surfaces, `--paper` background, `--ink` text | Whole page flips from near-black to warm white. Confirm the legal text is comfortably readable, headings still separate from body, and no element kept a dark background it now sits alone on. **Done, `65c501e`.** Headings now 18.09:1, paragraphs 5.60:1. No invisible text — swept for elements whose colour equals the background, found none. **Two things to judge:** the 13px meta and footer lines are `--dim` at only **2.94:1** and fail AA (they failed on dark too, at 2.66 and 2.03), and the dividers are now `rgba(58,53,48,.12)` — confirm they read as separators and not as smudges. |
| P2 | `core/privacy.html` | `/privacy` | Same as P1 | Same as P1. Should end up visually identical in treatment to `/terms`. **Done, `65c501e`.** Headings now 18.09:1, paragraphs 5.60:1. No invisible text — swept for elements whose colour equals the background, found none. **Two things to judge:** the 13px meta and footer lines are `--dim` at only **2.94:1** and fail AA (they failed on dark too, at 2.66 and 2.03), and the dividers are now `rgba(58,53,48,.12)` — confirm they read as separators and not as smudges. |
| P3 | `core/dashboard.html` onboarding modal | `/dashboard`, new users only | **Was a dark panel.** `#111111` → `var(--card)`; backdrop `rgba(0,0,0,0.92)` → `rgba(var(--ink-rgb),0.55)`; text `#ffffff`/`#888888`/`#555555` → `--ink`/`--muted`/`--dim` | Modal is now a white card on a dimmed page. **Judge the scrim specifically** — 55% ink is my number, not a palette value. Too light and the modal stops feeling modal; too heavy and it reads as a takeover. Also confirm the three text levels still rank: heading darkest, then secondary, then the faintest label. Trigger it with a new account. |

---

## Authenticated pages — you check these

| Page | Route | Changed | What to look for |
|---|---|---|---|
| `core/dashboard.html` | `/dashboard` | `:root` removed, 26 vars + 26 literals remapped | Amber accents shift from `#f59e0b` to `#c8820a` — slightly deeper, less yellow **[C1]**. Hover amber deeper **[C3]**. Card corners 14px → **12px**, subtle; check cards and buttons. Transitions pick up the springier landing easing **[C15]**. Secondary text `#6b6259` → `#6b6157`, should be imperceptible. Status pills (green/red) deliberately unchanged. |
| `core/wizard.html` | `/consult/<slug>` | `:root` removed, 17 vars + 7 literals remapped | Same amber shift **[C1]** and deeper hover **[C3]**. The two `#f59e0b` washes behind step indicators become `#c8820a`. Submit button label stays white on amber. Page background unchanged. |
| `core/answer.html` | `/answer/<id>` | `:root` removed, 14 vars + 24 literals remapped | **The dark hero is meant to stay dark** — `.ans-hero` is a radial gradient onto `#0d0d0d` with white text, same two-tone pattern as landing. So is the black `.btn-rera` CTA. If either has gone light, that is a bug. Otherwise: 19 amber washes shift `#f59e0b` → `#c8820a` **[C1]**, hover deeper **[C3]**. Body text was `rgba(28,25,22,.87)` and is unchanged in value. Green `#16a34a` "copied" state deliberately untouched. |
| `lawyers/browse.html` | `/lawyers/` | `:root` removed, 38 vars + 19 literals remapped | Amber **[C1]**, hover **[C3]**, corners 14px → **12px**, easing **[C15]**. Filter and search **input fields** were raw `#ffffff`/`#1c1916` and are now `--card`/`--ink` — same values, but check the inputs specifically since they were the only elements styled outside the token system. Green "verified" badge unchanged. |
| `lawyers/profile.html` | `/lawyers/<id>` | `:root` removed, 59 vars + 11 literals remapped | Amber **[C1]**, hover **[C3]**, corners 14px → **12px**, easing **[C15]**. Largest var remap so far (59), so give the whole page a general look. **Star rating: see the warning below.** Status colours (green/red/blue/teal) deliberately untouched. |
| `core/credits.html` | `/credits` | `:root` removed, 41 vars + 12 literals remapped | **Biggest amber shift of any page** — this page's `:root` carried the *admin* amber (`#f59e0b`/`#d97706`), so 9 accent call sites plus 3 washes all move to `#c8820a` **[C1]** and 3 hovers to `#a86a08` **[C3]**. Look at the pricing cards and the buy buttons. **Also: the credit ledger amounts.** Positive was light green `#4ade80`, negative light red `#f87171`; both are now the darker status tokens. Check they still read as clearly positive/negative. Corners 14px → 12px, easing **[C15]**. |
| `core/history.html` | `/history` | `:root` removed, 18 vars + 10 literals remapped | Amber **[C1]**, hover **[C3]**, corners 14px → **12px**, easing **[C15]**. **Known gap:** the completed-status pills keep a light-green *background* while their text moved to the darker success token — the pill may look washed out until the success-channel question is settled. Not a bug, a logged stop. |

| `lawyers/dashboard.html` | `/lawyers/dashboard` | `:root` removed, 62 vars + 32 literals remapped | Amber **[C1]**, hover **[C3]**, corners 14px → **12px**, easing **[C15]**. **Booking status pills** are the thing to look at — their backgrounds were light green/red/blue washes under dark text and now derive from the darker status tokens, so pill and label finally share a hue. Info blue is value-identical, so it should look untouched. |
| `lawyers/register.html` | `/lawyers/register` | `:root` removed, 22 vars + 15 literals remapped | Amber **[C1]**, hover **[C3]**, corners 14px → **12px**. The two **required-field markers** move from light `#f87171` to the darker `--error-text`. |
| `lawyers/review.html` | `/lawyers/review/<id>` | `:root` removed, 19 vars + 10 literals remapped | Amber **[C1]**, hover **[C3]**. **Two things to trigger:** the required-rating asterisk, and submitting with no rating — the validation outline was `#ef4444` and is now `--error-text`, noticeably darker. |
| `core/answer.html` (follow-up) | `/answer/<id>` | 2 black surfaces tokenised | The `.btn-rera` CTA and the rule above the RERA section moved from pure `#000` to `--ink-2` (`#0e0c0a`). Warm near-black instead of true black — subtle, but check the CTA still reads as deliberately heavy. |
| `lawyers/edit_profile.html` | `/lawyers/edit-profile` | `:root` removed, 20 vars + 6 literals remapped | Amber **[C1]**, hover **[C3]**. The two **required-field markers** move from light `#f87171` to the darker `--error-text`, matching profile.html. |

---

## Public pages — I screenshot these

| Page | Route | Changed | Status |
|---|---|---|---|
| `core/landing.html` | `/` | 25 literals → tokens, all value-identical | Verified live: every token resolves to its original value, `.on-dark .section-h` still computes `rgb(248,246,242)`. **Expect zero visible change.** Still to do at Step 7: check the Burj Khalifa hero against the new red once Step 5 lands. |
| `core/for_lawyers.html` | `/for-lawyers` | Font load + 47 literals tokenised | Two things. **(1)** Bold text is now the **real** DM Sans 700 cut, not synthesised faux-bold — headings should look cleaner. **(2)** This page carried more stale values than any other: nav/logo accent `#f5a623` → `#e0a040` **[C2]**, hovers **[C3]**, the "why" band `#f2ede6` → `#f0ece6` **[C5]**. The dark hero stays dark (D5) but its overlay moved from pure black to warm ink — check the hero photo still reads well through it. |
| `core/terms.html` | `/terms` | See **P1** | Not yet done |
| `core/privacy.html` | `/privacy` | See **P2** | Not yet done |
| 4 auth pages | `/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/reset-password/<token>` | password-toggle `#555` → `--dim`, hover `#f59e0b` → `--amber` | **Done.** `login` and `reset_password` fully tokenised; `forgot_password` needed nothing. Verified live with a hard reload. Only change: the show/hide toggle is slightly lighter and its hover slightly deeper. |
| `lawyers/login.html` | `/lawyers/login` | fully tokenised, zero literals | Same toggle change as the auth pages. |
| 6 error pages | — | — | Not yet done |

---

## Applies to every page

- **The font merge.** Four DM Sans loads became one. Every routed page should
  still render DM Sans; if any page falls back to a system sans, that is a
  regression. Verified live on `/`, `/terms`, `/for-lawyers`.
- **No dark mode.** No `prefers-color-scheme` block was added anywhere.
- **Admin is exempt** and stays dark on Inter. `/admin/*` is out of scope.

## Closed — the star rating now follows the palette

Was a gap; fixed in `d8af096`. The rating script's colour strings are tokens
now, so the stars will go crimson with everything else at Step 5.

**One real change to look at on `/lawyers/<id>`:** the required-field asterisk
and the "not enough credits" message were `#f87171`, a light red, on a light
card. They are now `--error-text` `#991b1b` — **noticeably darker**. Contrast is
better, but judge whether it reads as too heavy for a small inline marker.

Unlit stars moved `#555` → `--dim`, matching the onboarding modal's tertiary
text. Slightly lighter and warmer than before.

## The two-tone is deliberate

After Step 5, **the landing hero and the answer-page hero stay near-black**
while the rest of the app is warm white. That is the dark-surface rule (D5)
working as intended, not a page that failed to migrate.

`terms` and `privacy` were dark and are being converted, because a page of
reading text is not a hero.

## Check the progress tracks

`.read-progress-bar` (the reading-progress strip on `/answer/<id>`) and
`.progress-seg` now use `--rule` as a solid fill instead of an opaque grey.

**The track must be visible but clearly quieter than the filled portion.** At 12%
ink over warm white it should read as a faint recessed line. If it looks too
faint to register as a track, that is a one-number adjustment at Step 6 — not a
new token.

## Not to be alarmed by

- **Status colours are partly migrated.** Solid greens/reds now use
  `--success-text` / `--error-text` and will follow D7. Their **washes**
  (`rgba(74,222,128,a)` etc.) cannot — no channel token exists — so pill
  backgrounds will still look un-migrated after Step 5. Logged as F12.
- **Button label text** stays `#fff` / `#000000`. There is no white or black
  *text* token; `--card` is a surface. Logged, not an oversight.
