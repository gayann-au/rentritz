#!/usr/bin/env node
/**
 * apply-brand-map.mjs — the F13 property pass.
 *
 * The accent ramp cannot map token-to-token. --amber is used as TEXT more than
 * as fill (107 color: sites against 62 backgrounds), and R1 is explicit that
 * --brand is fills only while --brand-deep is the token for red text on light.
 * A 1:1 rename would put #D6263A on light backgrounds as text in 107 places.
 *
 * So the CSS PROPERTY decides, with no judgement per site:
 *
 *     color:                                     -> --brand-deep
 *     background / background-color / fill       -> --brand
 *     gradient stops                             -> --brand
 *     border-color / border shorthand / outline  -> --brand
 *     box-shadow                                 -> --brand
 *     stroke  (SVG icon beside text)             -> --brand-deep
 *
 * ONE manual review is still required afterwards, and this script cannot do it:
 * color: var(--amber) inside a DARK-surface rule. Deep crimson on near-black is
 * too dark; those need --brand or lighter. The script flags every candidate it
 * can see (a rule carrying a two-tone marker) under REVIEW instead of silently
 * rewriting it.
 *
 * Usage:
 *     node scripts/apply-brand-map.mjs                 dry run, prints a plan
 *     node scripts/apply-brand-map.mjs --apply         writes the changes
 *     node scripts/apply-brand-map.mjs --self-test     proves the mapping logic
 *
 * Run the dry run and read it before ever passing --apply.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

/** Source tokens the ramp collapses from. Names, not values. */
const RAMP = ['--amber', '--amber-soft', '--amber-2'];

/** Property -> destination token. The whole decision table. */
const TEXT_PROPS = new Set(['color', 'stroke', '-webkit-text-fill-color']);
const FILL_PROPS = new Set([
  'background', 'background-color', 'background-image', 'fill',
  'border', 'border-color', 'border-top', 'border-right', 'border-bottom',
  'border-left', 'border-top-color', 'border-right-color',
  'border-bottom-color', 'border-left-color', 'outline', 'outline-color',
  'box-shadow', 'text-shadow', 'caret-color', 'accent-color',
  'column-rule-color', 'text-decoration-color',
]);

const URL_SCHEMES = new Set(['mailto', 'tel', 'http', 'https', 'data', 'url']);

/**
 * The SOURCE TOKEN carries the light/dark signal. This is the important bit.
 *
 * A selector-name heuristic was tried first and was worse than useless: it
 * reported ZERO dark-context sites, because the amber text on dark heroes sits
 * on child classes (.fl-tag, .lf-brand span, .hero-h em), not on the container
 * it looked for. Zero review items read as "all clear" while 50 sites were at
 * risk of becoming unreadable.
 *
 * The codebase already encodes the distinction, consistently:
 *
 *     .eyebrow                { color: var(--amber)      }   on LIGHT
 *     .on-dark .eyebrow       { color: var(--amber-soft) }   on DARK
 *     .section-h em           { color: var(--amber)      }
 *     .on-dark .section-h em  { color: var(--amber-soft) }
 *
 * --amber and --amber-2 are the on-light accents; --amber-soft is the on-dark
 * accent. So for TEXT the source token decides, with no selector parsing and no
 * DOM knowledge:
 *
 *     color: --amber / --amber-2  ->  --brand-deep   #9B1B2B   on light
 *     color: --amber-soft         ->  --brand-light  #E8546A   on dark
 *
 * --brand-deep on near-black would be unreadable, which is exactly what this
 * prevents. Fills are unaffected: every ramp token maps to --brand there.
 */
const destinationFor = (prop, sourceToken) => {
  if (TEXT_PROPS.has(prop)) {
    return sourceToken === '--amber-soft' ? '--brand-light' : '--brand-deep';
  }
  if (FILL_PROPS.has(prop)) return '--brand';
  return null; // unknown property: never guess
};

const args = process.argv.slice(2);
const APPLY = args.includes('--apply');
const SELF_TEST = args.includes('--self-test');

/**
 * Rewrite one file's text.
 *
 * Walks declaration by declaration. The property is read from the declaration
 * itself, never from the line, because a line-start regex misses single-line
 * rules and would map text to a fill token.
 */
function rewrite(src) {
  const edits = [];
  const review = [];
  const lines = src.split('\n');

  let selector = '';
  const out = lines.map((line, idx) => {
    // remember the most recent selector prelude so a color: can be judged
    const selMatch = line.match(/^([^{}]*[.#][\w-][^{}]*)\{/);
    if (selMatch) selector = selMatch[1].trim();

    // a rule marked two-tone sits on a dark surface: roles invert there, so
    // deep crimson on near-black would be too dark. Never rewrite, always flag.
    const isTwoTone = /two-tone/i.test(line);

    return line.replace(
      // value must NOT cross a quote. Without that, an href="mailto:..." runs
      // greedily past the closing quote into the style="color:var(--amber)"
      // beside it, the match is skipped as a URL scheme, and the real
      // declaration never gets its own turn. That silently missed 7 sites.
      /([a-zA-Z-]+)\s*:\s*([^;{}"']+)/g,
      (whole, rawProp, value) => {
        const prop = rawProp.toLowerCase();
        // "mailto:", "tel:", "https:" look like declarations. Skipping them
        // matters: the real color: on the same line must still be rewritten.
        if (URL_SCHEMES.has(prop)) return whole;
        // the alias map's own definitions are retired deliberately at Step 5,
        // not by this pass
        if (rawProp.startsWith('--')) return whole;
        // which ramp tokens does this declaration actually mention?
        const present = RAMP.filter((t) =>
          new RegExp(`var\\(\\s*${t}\\s*\\)`).test(value) ||
          new RegExp(`var\\(\\s*${t}-rgb\\s*\\)`).test(value));
        if (!present.length) return whole;

        if (isTwoTone) {
          review.push({ line: idx + 1, prop, reason: 'two-tone marker', text: line.trim() });
          return whole;
        }
        if (!destinationFor(prop, present[0])) {
          review.push({ line: idx + 1, prop, reason: 'unmapped property', text: line.trim() });
          return whole;
        }

        // each source token gets its OWN destination, so a gradient mixing
        // --amber and --amber-soft resolves both correctly
        let v = value;
        for (const t of present) {
          const dest = destinationFor(prop, t);
          const before = v;
          v = v.replace(new RegExp(`var\\(\\s*${t}\\s*\\)`, 'g'), `var(${dest})`);
          v = v.replace(new RegExp(`var\\(\\s*${t}-rgb\\s*\\)`, 'g'), `var(${dest}-rgb)`);
          if (v !== before) edits.push({ line: idx + 1, prop, dest, src: t, text: line.trim() });
        }
        return whole.replace(value, v);
      });
  });

  return { text: out.join('\n'), edits, review };
}

// ── self test ────────────────────────────────────────────────────────────────
// Runs against the CURRENT token names, so the mapping is proven before it is
// ever pointed at the new ones.
if (SELF_TEST) {
  const cases = [
    ['color', '--brand-deep'], ['stroke', '--brand-deep'],
    ['background', '--brand'], ['background-color', '--brand'],
    ['background-image', '--brand'], ['fill', '--brand'],
    ['border', '--brand'], ['border-color', '--brand'],
    ['border-bottom', '--brand'], ['outline', '--brand'],
    ['box-shadow', '--brand'], ['accent-color', '--brand'],
    ['font-size', null], ['transform', null],
  ];
  let bad = 0;
  for (const [prop, want] of cases) {
    const got = destinationFor(prop, '--amber');
    const ok = got === want;
    if (!ok) bad += 1;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${prop.padEnd(22)} -> ${String(got)}`);
  }

  const sample = [
    '.a { color: var(--amber); }',
    '.b { background: var(--amber); }',
    '.c { border: 1px solid var(--amber-2); }',
    '.d { box-shadow: 0 2px 4px rgba(var(--amber-rgb),.3); }',
    '.e { background: linear-gradient(90deg,var(--amber) 0%,var(--amber-soft) 100%); }',
    '.f { color: var(--amber); } /* two-tone */',
    '.g { font-size: 1rem; }',
    '.h { color: var(--amber-soft); }',
    '.i { background: var(--amber-soft); }',
    '.j { background: linear-gradient(90deg,var(--amber),var(--amber-soft)); }',
  ].join('\n');
  const { text, edits, review } = rewrite(sample);
  console.log('\n  sample rewrite, using TODAY\'s token names:');
  for (const line of text.split('\n')) console.log(`    ${line}`);
  console.log(`\n  edits=${edits.length}  review=${review.length}`);

  const must = [
    ['.a { color: var(--brand-deep); }', 'color -> --brand-deep'],
    ['.b { background: var(--brand); }', 'background -> --brand'],
    ['border: 1px solid var(--brand)', 'border -> --brand'],
    ['rgba(var(--brand-rgb),.3)', 'channel form remapped'],
    ['linear-gradient(90deg,var(--brand) 0%,var(--brand) 100%)', 'gradient stops -> --brand'],
    ['.f { color: var(--amber); }', 'two-tone line left untouched'],
    ['.h { color: var(--brand-light); }', 'amber-soft as TEXT -> --brand-light (on dark)'],
    ['.i { background: var(--brand); }', 'amber-soft as FILL -> --brand'],
    ['.j { background: linear-gradient(90deg,var(--brand),var(--brand)); }', 'mixed gradient -> --brand'],
  ];
  for (const [needle, what] of must) {
    if (!text.includes(needle)) { console.error(`  FAIL: ${what}`); bad += 1; }
  }
  if (review.length !== 1) { console.error(`  FAIL: expected exactly 1 REVIEW, got ${review.length}`); bad += 1; }

  console.log(bad === 0 ? '\nself-test: PASS' : `\nself-test: FAIL (${bad} problem(s))`);
  process.exitCode = bad === 0 ? 0 : 1;
} else {
  const files = [join(ROOT, 'static/css/main.css')];
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.isDirectory()) {
        if (e.name === 'admin' || e.name === 'email') continue;
        walk(join(dir, e.name));
      } else if (e.name.endsWith('.html')) files.push(join(dir, e.name));
    }
  };
  if (existsSync(join(ROOT, 'templates'))) walk(join(ROOT, 'templates'));

  let totalEdits = 0;
  const allReview = [];
  for (const abs of files) {
    if (!existsSync(abs)) continue;
    const rel = abs.slice(ROOT.length + 1).replace(/\\/g, '/');
    const src = readFileSync(abs, 'utf8');
    const { text, edits, review } = rewrite(src);
    if (edits.length) {
      totalEdits += edits.length;
      console.log(`\n${rel}  (${edits.length} edits)`);
      const byDest = {};
      for (const e of edits) {
        const k = `${e.prop} -> ${e.dest}`;
        byDest[k] = (byDest[k] || 0) + 1;
      }
      for (const [k, n] of Object.entries(byDest).sort()) {
        console.log(`    ${String(n).padStart(3)}  ${k}`);
      }
    }
    for (const r of review) allReview.push({ rel, ...r });
    if (APPLY && edits.length) writeFileSync(abs, text, 'utf8');
  }

  console.log(`\n${APPLY ? 'APPLIED' : 'DRY RUN'} — ${totalEdits} edits`);
  if (allReview.length) {
    console.log(`\nMANUAL REVIEW REQUIRED — ${allReview.length} site(s) NOT rewritten:`);
    for (const r of allReview) {
      console.log(`  ${r.rel}:${r.line}  [${r.reason}] ${r.prop}`);
      console.log(`      ${r.text.slice(0, 90)}`);
    }
    console.log('\nThese are the dark-surface sites. Deep crimson on near-black is too');
    console.log('dark — decide --brand or lighter for each, by hand.');
  }
  if (!APPLY) console.log('\nNothing was written. Re-run with --apply once the plan above is right.');
}
