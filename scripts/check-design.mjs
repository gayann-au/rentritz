#!/usr/bin/env node
/**
 * check-design.mjs — guards the design token layer.
 *
 * Exists because of a real failure. A nested CSS comment in tokens.css, where
 * an inner terminator closed the OUTER comment, silently blanked EVERY token.
 * CSS comments do not nest, so everything after that point became garbage.
 * No console error, no build error, no test failure. Pages simply fell back
 * to unstyled defaults.
 *
 * Static checks alone would not have caught the whole class of problem either,
 * which is why the last check fetches the stylesheet over HTTP and asserts a
 * token is really present in the bytes the browser receives.
 *
 * Usage:
 *     node scripts/check-design.mjs
 *     node scripts/check-design.mjs --base-url=http://localhost:5000
 *     node scripts/check-design.mjs --skip-http     (static checks only)
 *
 * Exit code 0 = pass, 1 = at least one failure.
 */

import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

const CSS_FILES = ['static/css/tokens.css', 'static/css/main.css'];

/** Channel tokens Step 5 will edit. If these vanish, the palette is dead. */
const REQUIRED_TOKENS = [
  '--paper-rgb', '--paper-2-rgb', '--card-rgb', '--ink-rgb', '--ink-2-rgb',
  '--dark-rgb', '--muted-rgb', '--dim-rgb',
  // R1 brand ramp. --amber-rgb / --amber-soft-rgb / --amber-2-rgb and
  // --deep-grey-rgb were retired at Step 5a: the ramp collapsed by property
  // into brand / brand-deep / brand-light, and deep-grey dissolved into ink.
  '--brand-rgb', '--brand-deep-rgb', '--brand-soft-rgb', '--brand-light-rgb',
  '--action-rgb', '--error-rgb',
];

/** The token the HTTP check asserts on, per the brief. */
const HTTP_SENTINEL = '--paper-rgb';

const args = process.argv.slice(2);
const skipHttp = args.includes('--skip-http');
const baseUrl = (
  args.find((a) => a.startsWith('--base-url=')) || '--base-url=http://localhost:5000'
).split('=').slice(1).join('=');

const failures = [];
const notes = [];
const fail = (file, msg) => failures.push({ file, msg });

const OPEN = '/' + '*';
const CLOSE = '*' + '/';

/**
 * Walk a stylesheet and classify every comment delimiter.
 *
 * Deliberately NOT a naive count of openers vs terminators. A literal opener
 * sitting inside a comment (a glob in prose, say) inflates a naive count and
 * would report a mismatch on a perfectly valid file. This scanner only counts
 * delimiters that are structurally real.
 */
function scanComments(src) {
  const opens = [];
  const closes = [];
  const nested = [];
  let i = 0;
  let openedAt = -1;
  let inComment = false;

  while (i < src.length - 1) {
    const two = src.slice(i, i + 2);
    if (!inComment && two === OPEN) {
      inComment = true;
      openedAt = i;
      opens.push(i);
      i += 2;
      continue;
    }
    if (inComment && two === OPEN) {
      nested.push({ index: i, openedAt });
      i += 2;
      continue;
    }
    if (inComment && two === CLOSE) {
      inComment = false;
      closes.push(i);
      i += 2;
      continue;
    }
    i += 1;
  }
  return { opens, closes, nested, unterminated: inComment ? openedAt : -1 };
}

const lineOf = (src, index) => src.slice(0, index).split('\n').length;

/**
 * Blank comments but keep every offset intact.
 *
 * stripComments() shortens the text, so a line number computed on its output
 * does not address the same line in the original. Anything that needs to report
 * a position, or look back at the original line, must use this instead.
 */
function blankComments(src) {
  let out = '';
  let i = 0;
  let inComment = false;
  while (i < src.length) {
    if (!inComment && src.slice(i, i + 2) === OPEN) { inComment = true; out += '  '; i += 2; continue; }
    if (inComment && src.slice(i, i + 2) === CLOSE) { inComment = false; out += '  '; i += 2; continue; }
    out += inComment ? (src[i] === '\n' ? '\n' : ' ') : src[i];
    i += 1;
  }
  return out;
}

/** Remove comments so the remaining text can be checked structurally. */
function stripComments(src) {
  let out = '';
  let i = 0;
  let inComment = false;
  while (i < src.length) {
    if (!inComment && src.slice(i, i + 2) === OPEN) { inComment = true; i += 2; continue; }
    if (inComment && src.slice(i, i + 2) === CLOSE) { inComment = false; i += 2; continue; }
    if (!inComment) out += src[i];
    i += 1;
  }
  return out;
}

/**
 * Find "prop: value;" statements sitting at brace depth 0.
 *
 * Walks the (comment-free) source tracking depth. A depth-0 run of text that
 * terminates at "{" was a selector prelude and is discarded. One that
 * terminates at ";" is a complete top-level statement: legal if it is an
 * at-rule (@import, @charset), a bug if it looks like a declaration.
 */
function findTopLevelDeclarations(bare) {
  const found = [];
  let depth = 0;
  let buf = '';
  let bufStart = 0;

  for (let i = 0; i < bare.length; i += 1) {
    const ch = bare[i];
    if (ch === '{') {
      depth += 1;
      buf = '';
      bufStart = i + 1;
      continue;
    }
    if (ch === '}') {
      depth = Math.max(0, depth - 1);
      buf = '';
      bufStart = i + 1;
      continue;
    }
    if (depth !== 0) continue;

    if (ch === ';') {
      const stmt = buf.trim();
      const m = /^([a-zA-Z-]{2,})\s*:/.exec(stmt);
      if (m && !stmt.startsWith('@')) {
        found.push({
          prop: m[1].toLowerCase(),
          line: bare.slice(0, bufStart).split('\n').length,
        });
      }
      buf = '';
      bufStart = i + 1;
      continue;
    }
    if (buf === '' && /\s/.test(ch)) { bufStart = i + 1; continue; }
    buf += ch;
  }
  return found;
}

// ── static checks ────────────────────────────────────────────────────────────
for (const rel of CSS_FILES) {
  const abs = join(ROOT, rel);
  if (!existsSync(abs)) { fail(rel, 'file not found'); continue; }
  const src = readFileSync(abs, 'utf8');
  const { opens, closes, nested, unterminated } = scanComments(src);

  // 1. nested comment — the exact bug this script exists for
  for (const n of nested) {
    fail(rel,
      `nested comment: an opener on line ${lineOf(src, n.index)} sits inside the ` +
      `comment opened on line ${lineOf(src, n.openedAt)}. CSS comments do not nest — ` +
      `the first terminator closes the OUTER comment and silently voids ` +
      `everything after it.`);
  }

  // 2. unterminated comment
  if (unterminated !== -1) {
    fail(rel, `unterminated comment opened on line ${lineOf(src, unterminated)}`);
  }

  // 3. real open/close counts must match
  if (opens.length !== closes.length) {
    fail(rel, `comment delimiters unbalanced: ${opens.length} opener(s) vs ${closes.length} terminator(s)`);
  }

  const bare = stripComments(src);

  // 4. braces balance once comments are gone
  const open = (bare.match(/\{/g) || []).length;
  const close = (bare.match(/\}/g) || []).length;
  if (open !== close) fail(rel, `braces unbalanced: ${open} open vs ${close} close`);

  // 5. a declaration outside any block is what an early-terminated comment
  //    actually leaves behind. Catch the symptom, not only the cause.
  //
  //    Depth-aware scan, NOT a regex over blanked text: blanking the blocks
  //    removes the very braces that bound a match, so a selector's own colon
  //    (".btn-primary:hover") then matches greedily to the next semicolon
  //    anywhere in the file. Learned the hard way.
  //
  //    At depth 0 a statement ending in "{" is a selector prelude (fine) and
  //    one ending in ";" is an at-rule (fine) or a stray declaration (a bug).
  for (const stray of findTopLevelDeclarations(bare)) {
    fail(rel,
      `declaration "${stray.prop}:" on line ${stray.line} is outside any rule block ` +
      `— usually the debris of a comment that closed early`);
  }
}

// 6. achromatic literals used as a SURFACE.
//
//    #fff / #000 on a background is a surface and must be a token. On color:
//    they stay literal — that is the named achromatic exception for button
//    labels, where no white/black TEXT token exists.
//
//    This exists because the distinction was nearly missed by eye on
//    for_lawyers.html: four background:#fff were read as "button labels" when
//    they were card surfaces. Same error class as F13 — inferring role from
//    appearance instead of from the property. The property decides.
{
  const templateFiles = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (entry.name === 'admin' || entry.name === 'email') continue; // exempt
        walk(join(dir, entry.name));
      } else if (entry.name.endsWith('.html')) {
        templateFiles.push(join(dir, entry.name));
      }
    }
  };
  const tplRoot = join(ROOT, 'templates');
  if (existsSync(tplRoot)) walk(tplRoot);

  const SURFACE_LITERAL =
    /background(?:-color)?\s*:\s*[^;{}]*?(#fff\b|#ffffff\b|#000\b|#000000\b)/gi;

  for (const abs of [...templateFiles, join(ROOT, 'static/css/main.css')]) {
    if (!existsSync(abs)) continue;
    const rel = abs.slice(ROOT.length + 1).replace(/\\/g, '/');
    const src = stripComments(readFileSync(abs, 'utf8'));
    for (const m of src.matchAll(SURFACE_LITERAL)) {
      fail(rel,
        `"${m[1]}" is used as a SURFACE near line ${lineOf(src, m.index)} ` +
        `(${m[0].trim().slice(0, 60)}). Backgrounds must be tokens — use ` +
        `var(--card) for white, var(--ink-2) for black. On color: they may ` +
        `stay literal (the achromatic label exception).`);
    }
  }
}

// 7. ROLE DIRECTION. A surface token must not colour text, and a text token
//    must not paint a surface.
//
//    This is the failure mode nothing else can see: mapping color: to
//    --card-rgb was value-identical (both #ffffff), so no visual check, no
//    contrast check and no literal scan would ever have flagged it. It stays
//    invisible until Step 5 changes the token - at which point text silently
//    takes a surface colour.
//
//    TWO-TONE EXEMPTION. On a dark surface the roles legitimately invert:
//    "paper" becomes the text colour and "ink" becomes the background. That is
//    landing's and for_lawyers' hero treatment, kept under D5. Those rules opt
//    out explicitly with a marker comment on the same line, so every exemption
//    is visible in the source rather than hidden inside this script:
//
//        color: var(--paper);   two-tone
{
  const SURFACE_TOKENS = ['--card', '--paper', '--paper-2'];
  const TEXT_TOKENS = ['--ink', '--muted', '--dim'];
  const EXEMPT = /two-tone/i;

  // ALIAS RESOLUTION. main.css keeps a legacy name map (--white: var(--card),
  // --charcoal: var(--ink), ...). Without expanding it, "color: var(--white)"
  // reads as an unknown token and sails past - a surface colouring text,
  // through an alias, which is the exact error this check exists to stop.
  // 23 aliases, and expanding them exposed 11 sites the check could not see.
  const aliasMap = new Map();
  for (const f of ['static/css/main.css', 'static/css/tokens.css']) {
    const abs = join(ROOT, f);
    if (!existsSync(abs)) continue;
    const bare = stripComments(readFileSync(abs, 'utf8'));
    for (const m of bare.matchAll(/(--[\w-]+)\s*:\s*var\(\s*(--[\w-]+)\s*\)\s*;/g)) {
      aliasMap.set(m[1], m[2]);
    }
  }
  const resolveToken = (t) => {
    const seen = new Set();
    while (aliasMap.has(t) && !seen.has(t)) { seen.add(t); t = aliasMap.get(t); }
    return t;
  };

  // exact token match, alias-aware: var(--ink) must not also match
  // var(--ink-2) or var(--ink-rgb), but var(--charcoal) MUST match --ink.
  const usesToken = (value, token) => {
    for (const m of value.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)) {
      if (resolveToken(m[1]) === token) return true;
    }
    return false;
  };

  const roleFiles = [join(ROOT, 'static/css/main.css'), join(ROOT, 'static/css/tokens.css')];
  const walkTpl = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (entry.name === 'admin' || entry.name === 'email') continue;
        walkTpl(join(dir, entry.name));
      } else if (entry.name.endsWith('.html')) roleFiles.push(join(dir, entry.name));
    }
  };
  if (existsSync(join(ROOT, 'templates'))) walkTpl(join(ROOT, 'templates'));

  for (const abs of roleFiles) {
    if (!existsSync(abs)) continue;
    const rel = abs.slice(ROOT.length + 1).replace(/\\/g, '/');
    const raw = readFileSync(abs, 'utf8');
    // length-preserving, so reported line numbers and the marker lookup both
    // address the SAME coordinates as the original file
    const src = blankComments(raw);
    const rawLines = raw.split('\n');

    const scan = (propRe, tokens, label, advice) => {
      for (const m of src.matchAll(propRe)) {
        const value = m[2];
        const line = lineOf(src, m.index);
        // the marker lives in a comment, so check the ORIGINAL line
        if (EXEMPT.test(rawLines[line - 1] || '')) continue;
        for (const t of tokens) {
          if (!usesToken(value, t)) continue;
          fail(rel,
            `${label}: "${t}" on "${m[1]}" near line ${line}. ${advice} ` +
            `If this is a dark surface where the roles genuinely invert, add a ` +
            `two-tone marker comment on that line to opt out.`);
        }
      }
    };

    scan(/(?:^|[;{}\s"])(color)\s*:\s*([^;{}"]+)/g, SURFACE_TOKENS,
      'surface token colouring text',
      'Surfaces are for backgrounds; text should use --ink/--muted/--dim.');
    scan(/(?:^|[;{}\s"])(background|background-color)\s*:\s*([^;{}"]+)/g, TEXT_TOKENS,
      'text token painting a surface',
      'Text tokens are for type; surfaces should use --card/--paper/--paper-2.');
  }
}

// 8. the channel tokens Step 5 depends on must still be declared
const tokensAbs = join(ROOT, 'static/css/tokens.css');
if (existsSync(tokensAbs)) {
  const tokensSrc = stripComments(readFileSync(tokensAbs, 'utf8'));
  const missing = REQUIRED_TOKENS.filter((t) => !new RegExp(`${t}\\s*:`).test(tokensSrc));
  if (missing.length) {
    fail('static/css/tokens.css',
      `channel token(s) missing from a live declaration: ${missing.join(', ')}`);
  }
}

// 9. NO EMOJI, NO ITALICS.
//
//    Same shape as the nested-comment rule above: a whole class of problem
//    that nothing else can see, so it is asserted rather than eyeballed.
//    Emoji had leaked into 33 files and survived review because most of them
//    were not faces — they were arrows, checkmarks, stars and a warning
//    triangle, several of which read as ordinary punctuation in a diff.
//    Italics are worse: the type stack no longer requests an italic axis at
//    all, so a stray "font-style: italic" now renders as a SYNTHETIC oblique
//    rather than failing visibly.
//
//    ENTITIES COUNT. Half the emoji in this repo were written as "&#10003;"
//    or "&#x2B50;", not as literal characters. A scan for the codepoints
//    alone passed those straight through while the browser still painted the
//    glyph, so this decodes numeric and named entities and applies the same
//    ranges to the result. Otherwise the guard is one HTML escape away from
//    being bypassed by accident.
//
//    The geometric marks the admin panel uses for its icon language
//    (○ ◈ ◎ ◉ ◆, U+25C6..U+25CE) sit OUTSIDE these ranges and stay legal —
//    they are the sanctioned replacement, not an oversight.
{
  const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}\u{FE0F}\u{FE0E}\u{200D}]/u;
  const NAMED = {
    rarr: 0x2192, larr: 0x2190, uarr: 0x2191, darr: 0x2193, harr: 0x2194,
    rArr: 0x21d2, lArr: 0x21d0, uArr: 0x21d1, dArr: 0x21d3, hArr: 0x21d4,
    star: 0x2606, starf: 0x2605, check: 0x2713, cross: 0x2717,
    phone: 0x260e, sung: 0x266a, spades: 0x2660, clubs: 0x2663,
    hearts: 0x2665, diams: 0x2666,
  };
  const SKIP_DIRS = new Set([
    'node_modules', 'venv', '.venv', '__pycache__', '.git', '.claude',
    'landing', 'rentritz-landing', 'backups', 'uploads', 'instance', 'logs',
  ]);

  const inRanges = (cp) =>
    (cp >= 0x1f300 && cp <= 0x1faff) || (cp >= 0x2600 && cp <= 0x27bf) ||
    (cp >= 0x2190 && cp <= 0x21ff) || (cp >= 0x2b00 && cp <= 0x2bff) ||
    cp === 0xfe0f || cp === 0xfe0e || cp === 0x200d;

  /** Collect every source file the rule applies to: templates, CSS, JS, Python. */
  const collect = (dir, exts, out) => {
    if (!existsSync(dir)) return out;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(entry.name)) continue;
      const p = join(dir, entry.name);
      if (entry.isDirectory()) collect(p, exts, out);
      else if (exts.some((e) => entry.name.endsWith(e))) out.push(p);
    }
    return out;
  };

  const guarded = [
    ...collect(join(ROOT, 'templates'), ['.html'], []),
    ...collect(join(ROOT, 'static'), ['.css', '.js'], []),
    ...['app', 'config', 'scripts', 'migrations', 'tests']
      .flatMap((d) => collect(join(ROOT, d), ['.py'], [])),
    ...(existsSync(join(ROOT, 'run.py')) ? [join(ROOT, 'run.py')] : []),
  ];

  for (const abs of guarded) {
    const rel = abs.slice(ROOT.length + 1).replace(/\\/g, '/');
    const isTemplate = rel.endsWith('.html');

    readFileSync(abs, 'utf8').split('\n').forEach((line, i) => {
      const n = i + 1;

      // a. literal characters in the flagged ranges
      const lit = line.match(EMOJI);
      if (lit) {
        const cp = lit[0].codePointAt(0).toString(16).toUpperCase().padStart(4, '0');
        fail(rel, `emoji/pictograph "${lit[0]}" (U+${cp}) on line ${n}. Delete it, ` +
          `or use an inline Lucide SVG coloured with currentColor.`);
      }

      // b. the same codepoints smuggled in as an HTML entity
      for (const m of line.matchAll(/&#(x?)([0-9A-Fa-f]+);|&([A-Za-z][A-Za-z0-9]*);/g)) {
        const cp = m[3] ? NAMED[m[3]] : parseInt(m[2], m[1] ? 16 : 10);
        if (cp !== undefined && inRanges(cp)) {
          fail(rel, `HTML entity "${m[0]}" on line ${n} decodes to U+` +
            `${cp.toString(16).toUpperCase().padStart(4, '0')}, inside the banned ` +
            `emoji ranges. Escaping it does not make it a different glyph.`);
        }
      }

      // c. font-style: italic, and the synthetic-oblique sibling
      const fs = line.match(/font-style\s*:\s*(italic|oblique)/i);
      if (fs) {
        fail(rel, `"font-style: ${fs[1]}" on line ${n}. The webfont request no ` +
          `longer carries an italic axis, so this renders as a synthetic slant.`);
      }

      // d. an "italic" / "not-italic" class token
      for (const m of line.matchAll(/class\s*=\s*["']([^"']*)["']/g)) {
        const bad = m[1].split(/\s+/).find((c) => c === 'italic' || c === 'not-italic');
        if (bad) {
          fail(rel, `class "${bad}" on line ${n}. Italic styling is not available ` +
            `in this design system.`);
        }
      }

      // e. <i> and <em>. The lookahead keeps <img>, <input>, <iframe> and
      //    <embed> out of it — the tag name has to actually end there.
      if (isTemplate) {
        const tag = line.match(/<\/?(i|em)(?=[\s/>])/i);
        if (tag) {
          fail(rel, `<${tag[1]}> tag on line ${n}. Use <span> for a styling hook, ` +
            `or an inline SVG for an icon; neither <i> nor <em> may appear.`);
        }
      }
    });
  }
}

// ── the check that matters: what does the browser actually receive? ──────────
if (skipHttp) {
  notes.push('HTTP check skipped (--skip-http). Static checks only.');
} else {
  const url = `${baseUrl.replace(/\/$/, '')}/static/css/tokens.css`;
  try {
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) {
      fail(url, `server returned HTTP ${res.status}`);
    } else {
      const body = await res.text();
      if (!body.includes(HTTP_SENTINEL)) {
        fail(url,
          `served stylesheet does not contain "${HTTP_SENTINEL}". The file on disk can ` +
          `look fine while the bytes the browser receives are broken or stale.`);
      } else {
        notes.push(`HTTP ${HTTP_SENTINEL} present in ${url} (${body.length} bytes)`);
      }
    }
  } catch (err) {
    fail(url,
      `could not fetch (${err.cause?.code || err.message}). Start the app ` +
      `(preview, or python run.py) or pass --skip-http for static checks only.`);
  }
}

// ── report ───────────────────────────────────────────────────────────────────
for (const n of notes) console.log(`  ok   ${n}`);

if (failures.length === 0) {
  console.log('\ncheck-design: PASS');
} else {
  console.error(`\ncheck-design: FAIL — ${failures.length} problem(s)\n`);
  for (const f of failures) console.error(`  ${f.file}\n    ${f.msg}\n`);
}

// Set exitCode rather than calling process.exit(). On Windows, exiting while
// fetch's keep-alive socket is still open trips a libuv assertion and returns
// 127 — which would mask both PASS and FAIL. Letting the event loop drain
// naturally gives the honest code.
process.exitCode = failures.length === 0 ? 0 : 1;
