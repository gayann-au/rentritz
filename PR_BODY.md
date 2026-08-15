Presentation only. No routing, state, data or API changes.

**Do not deploy on merge.** Needs the visual review in `DESIGN_EYEBALL.md` first.

## What this does

Consolidates three drifting colour systems into one token layer, then swaps that
layer to the R1 Crimson palette. 68 commits, one page per commit for the
tokenising work.

## Read these two files first

- **`DESIGN_EYEBALL.md`** — the review checklist. Every one of the 26 pages, what
  changed, what to look for. Public and authenticated pages listed separately.
- **`DESIGN_MIGRATION.md`** — the decision record. Every ruling (D1–D7), every
  finding (F1–F14), and why.

## Two things the reviewer must do

1. **Start the server with `python run.py --dev`.** Without it Flask caches
   compiled templates and you will review stale markup. Startup prints
   `DEV MODE: template auto-reload ON`.
2. **Hard-reload every page** (Ctrl+Shift+R). A soft reload is not enough.

Every visual check made before this review is superseded and none is cited as
evidence — see F14.

## Structure

**Token layer.** Every colour derives from an `R,G,B` channel triplet:

    --brand-rgb: 214,38,58;
    --brand:     rgb(var(--brand-rgb));

That is what made the swap a one-file edit: Step 5a changed triplets and every
solid, wash, border and shadow followed.

**The accent ramp collapsed by PROPERTY, not by name.** `--amber` was used as
text more than as fill (118 vs 199), and R1 says `--brand` is fills only. A 1:1
rename would have put `#D6263A` on light backgrounds as text in ~125 places:

| | |
|---|---|
| `color:` | `--brand-deep` `#9B1B2B` |
| backgrounds, borders, gradients, shadows | `--brand` `#D6263A` |
| `color:` where the source was `--amber-soft` | `--brand-light` `#E8546A` — the on-dark accent |

Done by `scripts/apply-brand-map.mjs`, 378 edits, zero manual review items.

## Deliberate, not bugs

- **Two-tone survives.** The landing and answer heroes stay near-black (D5).
  Admin chrome stays dark and is exempt entirely.
- **Status colours are never crimson** (D7). Red is the brand now, so a red error
  would be indistinguishable from a brand element. Success → `--action`, error
  *and warning* → `--error` (deliberately amber), info unchanged.
- **`terms` and `privacy` converted from dark to light.** A page of reading text
  is not a hero.
- **`#fff`/`#000` button labels stay literals** — achromatic, no token needed.

## Checks

Two scripts, both green, run after every commit:

    node scripts/check-design.mjs      # 8 structural checks
    node scripts/check-contrast.mjs    # 28 WCAG pairs

`check-design.mjs` exists because a nested CSS comment silently blanked every
token with no error of any kind. It also catches surface-vs-text role errors,
resolving the 23-entry legacy alias map first.

`check-contrast.mjs`: **28 pairs, 0 failing.** Body text 17.9:1, brand-deep text
7.9:1, white on brand fill 5.0:1. `--brand-light` verified against the real hero
backgrounds (5.18–5.62), not against paper.

## Accessibility

Two pre-existing AA failures fixed, both measured rather than assumed:

| | before | after |
|---|---|---|
| `--dim` tertiary text, 72 sites | 2.94:1 | **4.66:1** |
| legal-page meta/footer, 13px | 2.94:1 | **5.60:1** |

The old amber was **2.92:1** on paper and had always failed AA. Crimson text at
`--brand-deep` is 7.9:1 — this migration removes a long-standing accessibility
failure rather than introducing one.

## Known open, tracked in `DESIGN_MIGRATION.md`

- **71 literals remain in `main.css`; 62 sit in confirmed-dead rules.** They
  render nothing, but **after this merge they still hold the old amber-era
  palette** — harmless while dead, an instant bug if anyone revives one of those
  classes. Covered by the D3 post-merge cleanup chore.
- **Guard gap:** `check-design.mjs` asserts the channel tokens *exist*, not that
  every `var()` reference still *resolves*. That is how `--rule-soft` pointed at
  a deleted channel for several commits.
- `--brand-soft` has **zero call sites**. Whoever first uses it must
  contrast-check the text placed on it.
- The Burj hero does not clash with crimson, but the eyebrow line and stat
  numbers sit over the bright part of the sky at low contrast. Text over a
  photo, so no script can measure it.

## Revert

    git checkout pre-r1-swap

Tagged immediately before the palette swap: all tokenising done, still amber.
