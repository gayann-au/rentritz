#!/usr/bin/env node
/**
 * check-contrast.mjs — WCAG contrast for every pair the palette produces.
 *
 * Reads the channel triplets straight out of tokens.css, so it cannot drift
 * from the palette: change a triplet and this recomputes.
 *
 * Thresholds (WCAG 2.x AA):
 *     4.5:1   normal text
 *     3.0:1   large text (>=18.66px bold, or >=24px) and UI / border contrast
 *
 * Exit 0 = every pair passes. Exit 1 = at least one fails.
 *
 *     node scripts/check-contrast.mjs
 *     node scripts/check-contrast.mjs --all     also print the passing pairs
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SHOW_ALL = process.argv.includes('--all');

// ── read the palette from tokens.css ────────────────────────────────────────
const css = readFileSync(join(ROOT, 'static/css/tokens.css'), 'utf8');
const channels = new Map();
for (const m of css.matchAll(/(--[\w-]+)-rgb:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*;/g)) {
  channels.set(m[1], [Number(m[2]), Number(m[3]), Number(m[4])]);
}
if (!channels.size) {
  console.error('No channel triplets found in tokens.css — has the format changed?');
  process.exit(1);
}

const hex = ([r, g, b]) =>
  '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('').toUpperCase();

/** WCAG relative luminance. */
const luminance = ([r, g, b]) => {
  const f = (v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};

const ratio = (fg, bg) => {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

const WHITE = [255, 255, 255];
const t = (name) => {
  const c = channels.get(name);
  if (!c) throw new Error(`token ${name} not found in tokens.css`);
  return c;
};

/**
 * Pairs that actually occur in the app.
 *
 * `min` is the threshold the pair must clear: 3.0 for large text and for
 * UI/border contrast, 4.5 for normal text. `note` says where the pair occurs,
 * because a column of numbers with no context is not reviewable.
 */
const PAIRS = [
  // ── light surfaces ───────────────────────────────────────────────────────
  ['body text',            '--ink',         '--paper',   4.5, 'every page'],
  ['body text on sunken',  '--ink',         '--paper-2', 4.5, 'auth + wizard pages'],
  ['body text on card',    '--ink',         '--card',    4.5, 'cards, modals'],
  ['deepest ink',          '--ink-2',       '--paper',   4.5, 'h1/h2 headings'],
  ['secondary text',       '--muted',       '--paper',   4.5, 'paragraphs, legal pages'],
  ['secondary on sunken',  '--muted',       '--paper-2', 4.5, 'auth pages'],
  ['secondary on card',    '--muted',       '--card',    4.5, 'card body copy'],
  ['tertiary text',        '--dim',         '--paper',   4.5, 'meta, placeholders, unlit stars'],
  ['tertiary on sunken',   '--dim',         '--paper-2', 4.5, 'auth page hints'],
  ['tertiary on card',     '--dim',         '--card',    4.5, 'card meta'],

  // ── brand ────────────────────────────────────────────────────────────────
  ['brand-deep text',      '--brand-deep',  '--paper',   4.5, 'ALL red text on light, ~125 sites'],
  ['brand-deep on card',   '--brand-deep',  '--card',    4.5, 'links and accents inside cards'],
  ['brand-deep on sunken', '--brand-deep',  '--paper-2', 4.5, 'accents on auth pages'],
  ['white on brand fill',  null,            '--brand',   4.5, 'every primary button label', WHITE],
  ['brand fill vs paper',  '--brand',       '--paper',   3.0, 'button and border edge, UI contrast'],
  ['brand fill vs card',   '--brand',       '--card',    3.0, 'buttons inside cards'],
  // INFORMATIONAL, threshold null. --brand-soft is a decorative background
  // tint, not a UI state indicator, so WCAG's 3:1 UI rule does not apply.
  // What matters is the contrast of whatever TEXT is placed on it, and that
  // pair cannot exist until something uses the token. It has ZERO call sites
  // today. Whoever first uses it must add the real text pair here.
  ['brand-soft vs paper',  '--brand-soft',  '--paper',   null, 'decorative tint, 0 call sites — check the TEXT on it when first used'],

  // ── signals. D7: never crimson. ──────────────────────────────────────────
  ['success text',         '--action',      '--paper',   4.5, 'success copy'],
  ['success on card',      '--action',      '--card',    4.5, 'status pills'],
  ['error text',           '--error',       '--paper',   4.5, 'error AND warning copy'],
  ['error on card',        '--error',       '--card',    4.5, 'field errors, required markers'],

  // ── dark surfaces. D5: heroes, full-bleed sections, admin chrome. ────────
  ['paper text on dark',   '--paper',       '--dark',    4.5, 'hero body copy'],
  ['paper text on ink',    '--paper',       '--ink',     4.5, 'footer and dark sections'],
  ['white on dark',        null,            '--dark',    4.5, 'hero headlines', WHITE],
  ['brand-light on dark',  '--brand-light', '--dark',    4.5, 'THE on-dark accent, 22 sites'],
  ['brand-light on ink',   '--brand-light', '--ink',     4.5, 'accents in the dark footer'],
  ['brand-light on ink-2', '--brand-light', '--ink-2',   4.5, 'accents on the deepest panels'],
  ['brand on dark',        '--brand',       '--dark',    3.0, 'brand fills inside dark sections'],
];

const rows = [];
for (const [name, fgTok, bgTok, min, note, fgLiteral] of PAIRS) {
  const fg = fgLiteral || t(fgTok);
  const bg = t(bgTok);
  const r = ratio(fg, bg);
  rows.push({
    name, note, min,
    fg: hex(fg), bg: hex(bg),
    r: Math.round(r * 100) / 100,
    // min === null means informational: reported, never failed
    pass: min === null ? true : r >= min,
    info: min === null,
  });
}

const w = Math.max(...rows.map((x) => x.name.length));
const fails = rows.filter((x) => !x.pass);
const infos = rows.filter((x) => x.info);

console.log(`\n  ${'pair'.padEnd(w)}  fg       bg       ratio   min  result`);
console.log(`  ${'-'.repeat(w)}  -------  -------  ------  ----  ------`);
for (const x of rows) {
  if (!SHOW_ALL && x.pass && !x.info) continue;
  console.log(
    `  ${x.name.padEnd(w)}  ${x.fg}  ${x.bg}  ${String(x.r).padStart(6)}  ` +
    `${String(x.min ?? '—').padStart(4)}  ${x.info ? 'info' : x.pass ? 'pass' : 'FAIL'}`
  );
}
const hidden = rows.length - fails.length - infos.length;
if (!SHOW_ALL && hidden > 0) {
  console.log(`\n  (${hidden} passing pairs hidden — use --all)`);
}

console.log(
  `\n  ${rows.length} pairs checked, ${fails.length} failing, ` +
  `${infos.length} informational.`
);

if (fails.length) {
  console.error('\nFAILING PAIRS\n');
  for (const x of fails) {
    console.error(`  ${x.name}`);
    console.error(`    ${x.fg} on ${x.bg} = ${x.r}:1, needs ${x.min}:1`);
    console.error(`    where: ${x.note}\n`);
  }
}
process.exitCode = fails.length ? 1 : 0;
