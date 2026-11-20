// md2pdf.mjs — offline Markdown -> PDF (A4), ohne pandoc/LibreOffice/Chromium.
// Bettet Lato (Regular/Bold) + IBM Plex Mono als TrueType ein; Text bleibt selektierbar.
// Aufruf: node md2pdf.mjs <in.md> <out.pdf> [--svg plan.svg] [--footer "text"]
import fs from 'node:fs';
import zlib from 'node:zlib';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require_ = createRequire(import.meta.url);
const RESVG_MODULE = '@resvg/resvg-js';
// resvg wird nur fuer --svg (Schaltbild-Seite) gebraucht und daher erst dort geladen.
function loadResvg() {
  try {
    return require_(RESVG_MODULE).Resvg;
  } catch (e) {
    throw new Error('md2pdf: resvg-js fehlt (nur fuer --svg noetig). Abhaengigkeit im Werkzeugordner bereitstellen. ' + e.message);
  }
}
const FONT_DIR = new URL('./fonts/', import.meta.url);
const fontPath = (name) => fileURLToPath(new URL(name, FONT_DIR));

/* ---------------- TrueType ---------------- */
function readTTF(file) {
  const buf = fs.readFileSync(file);
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const n = dv.getUint16(4);
  const T = {};
  for (let i = 0; i < n; i++) {
    const o = 12 + i * 16;
    const tag = String.fromCharCode(dv.getUint8(o), dv.getUint8(o + 1), dv.getUint8(o + 2), dv.getUint8(o + 3));
    T[tag] = { off: dv.getUint32(o + 8), len: dv.getUint32(o + 12) };
  }
  const upem = dv.getUint16(T.head.off + 18);
  const bbox = [dv.getInt16(T.head.off + 36), dv.getInt16(T.head.off + 38), dv.getInt16(T.head.off + 40), dv.getInt16(T.head.off + 42)];
  const asc = dv.getInt16(T.hhea.off + 4), desc = dv.getInt16(T.hhea.off + 6);
  const nH = dv.getUint16(T.hhea.off + 34);
  const cmap = new Map();
  const cOff = T.cmap.off, nSub = dv.getUint16(cOff + 2);
  let best = null;
  for (let i = 0; i < nSub; i++) {
    const p = cOff + 4 + i * 8;
    const pid = dv.getUint16(p), eid = dv.getUint16(p + 2), so = dv.getUint32(p + 4);
    if (dv.getUint16(cOff + so) === 4 && ((pid === 3 && eid === 1) || (pid === 0 && eid === 3))) { best = cOff + so; break; }
  }
  if (best !== null) {
    const segX2 = dv.getUint16(best + 6), seg = segX2 / 2;
    const endO = best + 14, startO = endO + segX2 + 2, deltaO = startO + segX2, rangeO = deltaO + segX2;
    for (let s = 0; s < seg; s++) {
      const end = dv.getUint16(endO + s * 2), start = dv.getUint16(startO + s * 2);
      const delta = dv.getInt16(deltaO + s * 2), ro = dv.getUint16(rangeO + s * 2);
      if (start === 0xffff) continue;
      for (let c = start; c <= end && c !== 0x10000; c++) {
        let g;
        if (ro === 0) g = (c + delta) & 0xffff;
        else {
          const gi = rangeO + s * 2 + ro + (c - start) * 2;
          if (gi + 1 >= buf.length) continue;
          g = dv.getUint16(gi);
          if (g !== 0) g = (g + delta) & 0xffff;
        }
        if (g && !cmap.has(c)) cmap.set(c, g);
      }
    }
  }
  const adv = (gid) => dv.getUint16(T.hmtx.off + Math.min(gid, nH - 1) * 4);
  return { buf, upem, bbox, asc, desc, cmap, adv };
}

const WINANSI = new Map([
  [0x20ac, 0x80], [0x201a, 0x82], [0x0192, 0x83], [0x201e, 0x84], [0x2026, 0x85], [0x2020, 0x86],
  [0x2021, 0x87], [0x02c6, 0x88], [0x2030, 0x89], [0x0160, 0x8a], [0x2039, 0x8b], [0x0152, 0x8c],
  [0x017d, 0x8e], [0x2018, 0x91], [0x2019, 0x92], [0x201c, 0x93], [0x201d, 0x94], [0x2022, 0x95],
  [0x2013, 0x96], [0x2014, 0x97], [0x02dc, 0x98], [0x2122, 0x99], [0x0161, 0x9a], [0x203a, 0x9b],
  [0x0153, 0x9c], [0x017e, 0x9e], [0x0178, 0x9f],
]);
const ASCII_FALLBACK = new Map([
  [0x2192, '->'], [0x2190, '<-'], [0x25b6, '>'], [0x25ba, '>'], [0x2500, '-'], [0x2502, '|'],
  [0x251c, '+'], [0x2514, '+'], [0x2510, '+'], [0x250c, '+'], [0x2534, '+'], [0x252c, '+'],
  [0x253c, '+'], [0x2265, '>='], [0x2264, '<='], [0x2248, '~'], [0x2260, '!='], [0x2009, ' '], [0x2212, '-'], [0x2011, '-'], [0x00ad, '-'],
  [0x200b, ''], [0x2003, ' '],
]);
const REV = new Map([...WINANSI.entries()].map(([u, c]) => [c, u]));
function winCode(cp) {
  if (WINANSI.has(cp)) return WINANSI.get(cp);
  if ((cp >= 32 && cp <= 126) || (cp >= 160 && cp <= 255)) return cp;
  return 63;
}
function sanitize(str) {
  let out = '';
  for (const ch of str) {
    const cp = ch.codePointAt(0);
    if (cp === 0x09) { out += '    '; continue; }
    if (cp === 0x0a || cp === 0x0d) { out += ' '; continue; }
    if (cp < 32) continue;
    if (WINANSI.has(cp) || (cp >= 32 && cp <= 126) || (cp >= 160 && cp <= 255)) { out += ch; continue; }
    if (ASCII_FALLBACK.has(cp)) { out += ASCII_FALLBACK.get(cp); continue; }
    out += '?';
  }
  return out;
}

class Font {
  constructor(file, name) {
    const t = readTTF(file);
    this.name = name; this.t = t; this.k = 1000 / t.upem;
    this.widths = [];
    for (let c = 32; c <= 255; c++) {
      const g = t.cmap.get(REV.get(c) ?? c);
      this.widths.push(g ? Math.round(t.adv(g) * this.k) : 0);
    }
  }
  w(str, size) {
    let s = 0;
    for (const ch of str) s += this.widths[winCode(ch.codePointAt(0)) - 32] || 0;
    return (s * size) / 1000;
  }
  enc(str) {
    let s = '';
    for (const ch of str) s += String.fromCharCode(winCode(ch.codePointAt(0)));
    return s;
  }
}

/* ---------------- PDF ---------------- */
const esc = (s) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
const num = (n) => (Math.round(n * 1000) / 1000).toString();
// part2

const PAGE = { w: 595.28, h: 841.89 };
const M = { l: 56, r: 56, t: 92, b: 62 };
const COL = {
  ink: [0.10, 0.10, 0.11], muted: [0.36, 0.39, 0.44], soft: [0.55, 0.58, 0.62],
  accent: [0.12, 0.37, 0.75], rule: [0.78, 0.80, 0.83], thbg: [0.925, 0.937, 0.952],
  codebg: [0.965, 0.965, 0.955],
};

function loadDoc(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  let i = 0;
  if (lines[0].trim() === '---') { i = 1; while (i < lines.length && lines[i].trim() !== '---') i++; i++; }
  const blocks = [];
  for (; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!t) continue;
    if (t.startsWith('```')) {
      const buf = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) { buf.push(lines[i]); i++; }
      blocks.push({ t: 'code', lines: buf }); continue;
    }
    if (/^<!--\s*(GRAFIK|LAYOUT|WIRING)\s*-->$/.test(t)) { blocks.push({ t: 'marker', name: t.replace(/[<!>\s-]/g, '') }); continue; }
    if (/^#{1,4}\s+/.test(t)) { blocks.push({ t: 'h', lvl: t.match(/^#+/)[0].length, text: t.replace(/^#+\s+/, '') }); continue; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { blocks.push({ t: 'hr' }); continue; }
    if (t.startsWith('>')) {
      const buf = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) { buf.push(lines[i].trim().replace(/^>\s?/, '')); i++; }
      i--; blocks.push({ t: 'quote', lines: buf }); continue;
    }
    if (/^\|/.test(t)) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) {
        const cells = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      i--; blocks.push({ t: 'table', rows }); continue;
    }
    if (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i])) {
      const items = [];
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
        const ind = lines[i].match(/^\s*/)[0].length;
        const mt = lines[i].trim();
        items.push({ ind, text: mt.replace(/^([-*]|\d+\.)\s+/, ''), num: /^\d+\./.test(mt) ? mt.match(/^(\d+)\./)[1] : null });
        i++;
      }
      i--; blocks.push({ t: 'list', items }); continue;
    }
    blocks.push({ t: 'p', text: t });
  }
  return blocks;
}

function parseInline(text) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m;
  const push = (s, o) => { if (s) runs.push(Object.assign({ text: s }, o)); };
  while ((m = re.exec(text))) {
    push(text.slice(last, m.index), {});
    const tok = m[0];
    if (tok.startsWith('**')) push(tok.slice(2, -2), { bold: true });
    else if (tok.startsWith('`')) push(tok.slice(1, -1), { mono: true });
    else if (tok.startsWith('[')) { const mm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/); push(mm[1], { link: mm[2] }); }
    else push(tok.slice(1, -1), {});
    last = m.index + tok.length;
  }
  push(text.slice(last), {});
  return runs;
}

class Renderer {
  constructor(fonts) {
    this.f = fonts; this.pages = []; this.cur = null;
    this.newPage();
  }
  newPage(w = PAGE.w, h = PAGE.h, bare = false) {
    this.cur = { w, h, ops: [], bare };
    this.pages.push(this.cur);
    this.y = M.t;
    this.maxY = h - M.b;
  }
  op(s) { this.cur.ops.push(s); }
  color(c, stroke) { this.op(num(c[0]) + ' ' + num(c[1]) + ' ' + num(c[2]) + ' ' + (stroke ? 'RG' : 'rg')); }
  rect(x, y, w, h, fill, stroke) {
    if (fill) this.color(fill);
    if (stroke) this.color(stroke, true);
    this.op(num(x) + ' ' + num(this.cur.h - y - h) + ' ' + num(w) + ' ' + num(h) + ' re ' + (fill && stroke ? 'B' : fill ? 'f' : 'S'));
  }
  line(x1, y1, x2, y2, c, lw) {
    const l = lw || 0.6;
    this.color(c, true);
    this.op(num(l) + ' w ' + num(x1) + ' ' + num(this.cur.h - y1) + ' m ' + num(x2) + ' ' + num(this.cur.h - y2) + ' l S');
  }
  text(x, yTop, str, font, size, c) {
    if (!str) return;
    this.color(c || COL.ink);
    this.op('BT /' + font + ' ' + num(size) + ' Tf ' + num(x) + ' ' + num(this.cur.h - yTop) + ' Td (' + esc(this.f[font].enc(sanitize(str))) + ') Tj ET');
  }
  wrap(runs, width, size) {
    const lines = []; let cur = []; let w = 0;
    const put = (text, font, sz, color, link) => { cur.push({ text, font, size: sz, color, link }); w += this.f[font].w(sanitize(text), sz); };
    for (const r of runs) {
      const font = r.mono ? 'F3' : r.bold ? 'F2' : 'F1';
      const sz = r.mono ? size - 0.35 : size;
      for (const part of r.text.split(/(\s+)/).filter((s) => s.length)) {
        if (/^\s+$/.test(part)) {
          if (!cur.length) continue;
          if (w + this.f[font].w(' ', sz) <= width) put(' ', font, sz, r.color);
          continue;
        }
        const pw = this.f[font].w(sanitize(part), sz);
        if (w + pw > width && cur.length) {
          while (cur.length && cur[cur.length - 1].text === ' ') cur.pop();
          lines.push(cur); cur = []; w = 0;
        }
        put(part, font, sz, r.color, r.link);
      }
    }
    while (cur.length && cur[cur.length - 1].text === ' ') cur.pop();
    if (cur.length) lines.push(cur);
    return lines.length ? lines : [[]];
  }
  drawLine(line, x, yTop, c) {
    let cx = x;
    for (const r of line) {
      this.text(cx, yTop, r.text, r.font, r.size, r.color || c);
      cx += this.f[r.font].w(sanitize(r.text), r.size);
    }
    const limit = this.cur.w - M.r + 0.5;
    if (cx > limit) {
      this.overflows = this.overflows || [];
      const txt = line.map((r) => r.text).join('').slice(0, 60);
      this.overflows.push((cx - limit).toFixed(1) + 'pt @y' + Math.round(yTop) + ': ' + txt);
    }
  }
  ensure(h) { if (this.y + h > this.maxY) this.newPage(); }
  heading(lvl, text) {
    const conf = lvl === 1 ? { s: 16.5, gap: 6, before: 0, c: COL.ink }
      : lvl === 2 ? { s: 12.6, gap: 5, before: 14, c: COL.ink }
        : { s: 10.4, gap: 4, before: 10, c: [0.16, 0.20, 0.26] };
    if (lvl >= 2) this.y += conf.before;
    const lines = this.wrap(parseInline(text), PAGE.w - M.l - M.r, conf.s);
    this.ensure(lines.length * (conf.s + conf.gap) + 4);
    for (const ln of lines) {
      this.y += conf.s;
      this.drawLine(ln, M.l, this.y, conf.c);
      this.y += conf.gap - 1;
    }
    if (lvl === 1) { this.y += 2; this.line(M.l, this.y, PAGE.w - M.r, this.y, COL.accent, 1.2); this.y += 10; }
  }
  paragraph(text, size, c, lead, indent) {
    const s = size || 9.4, col = c || COL.ink, ld = lead || 13.2, ind = indent || 0;
    const lines = this.wrap(parseInline(text), PAGE.w - M.l - M.r - ind, s);
    for (const ln of lines) {
      this.ensure(ld);
      this.y += s;
      this.drawLine(ln, M.l + ind, this.y, col);
      this.y += ld - s;
    }
    this.y += 3.5;
  }
  list(items) {
    for (const it of items) {
      const indent = 14 + (it.ind >= 2 ? 12 : 0);
      const lines = this.wrap(parseInline(it.text), PAGE.w - M.l - M.r - indent, 9.4);
      for (let k = 0; k < lines.length; k++) {
        this.ensure(13.2);
        this.y += 9.4;
        if (k === 0) this.text(M.l + indent - 9.5, this.y, it.num ? it.num + '.' : '\u2022', 'F1', 9.4, COL.accent);
        this.drawLine(lines[k], M.l + indent, this.y, COL.ink);
        this.y += 13.2 - 9.4;
      }
      this.y += 1.2;
    }
    this.y += 2.5;
  }
// probe
  quote(lines) {
    const pad = 9, barW = 2.2;
    const inner = PAGE.w - M.l - M.r - pad - 8;
    const parts = [];
    let total = 6;
    for (const l of lines) {
      if (!l.trim()) { parts.push(null); total += 4; continue; }
      const w = this.wrap(parseInline(l), inner, 8.8);
      parts.push(w);
      total += w.length * 12.2 + 2;
    }
    if (this.y + total > this.maxY) this.newPage();
    const y0 = this.y;
    let yy = y0 + 2;
    for (const p of parts) {
      if (!p) { yy += 4; continue; }
      for (const ln of p) {
        yy += 8.8;
        this.drawLine(ln, M.l + pad + 8, yy, [0.29, 0.32, 0.37]);
        yy += 3.4;
      }
      yy += 2;
    }
    this.line(M.l + pad, y0 + 1, M.l + pad, y0 + total - 5, COL.accent, barW);
    this.y = y0 + total + 4;
  }
  table(rows) {
    if (!rows.length) return;
    const fs0 = 7.7, padX = 4, padY = 3.6, lead = 10.1;
    const cols = Math.max.apply(null, rows.map((r) => r.length));
    const avail = PAGE.w - M.l - M.r;
    const nat = new Array(cols).fill(26);
    rows.forEach((r, ri) => {
      for (let c = 0; c < cols; c++) {
        const txt = (r[c] || '').replace(/[*`]/g, '');
        const wmax = this.f[ri === 0 ? 'F2' : 'F1'].w(txt, fs0) + padX * 2;
        nat[c] = Math.max(nat[c], Math.min(wmax, avail * 0.5));
      }
    });
    let widths = nat.slice();
    let sum = widths.reduce((a, b) => a + b, 0);
    if (sum > avail) {
      const minW = 30;
      let shrink = 0;
      for (const w of widths) shrink += Math.max(w - minW, 0);
      if (!shrink) shrink = 1;
      widths = widths.map((w) => w - (sum - avail) * Math.max(w - minW, 0) / shrink);
    } else if (sum < avail) {
      const extra = avail - sum;
      widths = widths.map((w) => w + extra * (w / sum));
    }
    const body = rows.map((r, ri) => {
      const cells = [];
      for (let c = 0; c < cols; c++) {
        const runs = parseInline((r[c] || '').replace(/\s+/g, ' '));
        if (ri === 0) for (const x of runs) x.bold = true;
        cells.push(this.wrap(runs, widths[c] - padX * 2, fs0));
      }
      let lines = 1;
      for (const cl of cells) lines = Math.max(lines, cl.length);
      return { cells, h: lines * lead + padY * 2 };
    });
    const self = this;
    const drawRow = function (row, y0, head) {
      if (head) self.rect(M.l, y0, avail, row.h, COL.thbg);
      row.cells.forEach((cl, c) => {
        let x = M.l;
        for (let i = 0; i < c; i++) x += widths[i];
        cl.forEach((ln, k) => self.drawLine(ln, x + padX, y0 + padY + 7.2 + k * lead, COL.ink));
      });
      self.line(M.l, y0 + row.h, M.l + avail, y0 + row.h, COL.rule, 0.7);
    };
    for (let ri = 0; ri < body.length; ri++) {
      const row = body[ri];
      if (this.y + row.h > this.maxY) {
        this.newPage();
        if (ri > 0) { drawRow(body[0], this.y, true); this.y += body[0].h; }
      }
      drawRow(row, this.y, ri === 0);
      this.y += row.h;
    }
    this.y += 8;
  }
  code(lines) {
    const padX = 6, padY = 6;
    let fs0 = 7.4;
    const avail = PAGE.w - M.l - M.r - padX * 2;
    let maxw = 0;
    for (const l of lines) maxw = Math.max(maxw, this.f.F3.w(l, fs0));
    if (maxw > avail) fs0 = Math.max(5.2, fs0 * avail / maxw);
    const lead = fs0 * 1.28;
    const h = lines.length * lead + padY * 2;
    if (this.y + h > this.maxY) this.newPage();
    const y0 = this.y;
    this.rect(M.l, y0, PAGE.w - M.l - M.r, h, COL.codebg, COL.rule);
    lines.forEach((l, k) => this.text(M.l + padX, y0 + padY + fs0 * 0.95 + k * lead, l, 'F3', fs0, [0.13, 0.17, 0.22]));
    this.y = y0 + h + 8;
  }
  imagePage(svgText) {
    const Resvg = loadResvg();
    const img = new Resvg(svgText, {
      fitTo: { mode: 'zoom', value: 3 },
      font: {
        fontFiles: [fontPath('Lato-Regular.ttf'), fontPath('Lato-Bold.ttf')],
        loadSystemFonts: false, defaultFontFamily: 'Lato',
      },
    }).render();
    const iw = img.width, ih = img.height, px = img.pixels;
    const rgb = Buffer.alloc(iw * ih * 3);
    let j = 0;
    for (let i = 0; i < px.length; i += 4) {
      const a = px[i + 3] / 255;
      rgb[j++] = Math.round(px[i] * a + 255 * (1 - a));
      rgb[j++] = Math.round(px[i + 1] * a + 255 * (1 - a));
      rgb[j++] = Math.round(px[i + 2] * a + 255 * (1 - a));
    }
    const pw = 841.89, ph = 595.28;
    this.newPage(pw, ph, true);
    this.cur.image = { w: iw, h: ih, data: zlib.deflateSync(rgb, { level: 9 }) };
    this.op('q ' + num(pw) + ' 0 0 ' + num(ph) + ' 0 0 cm /Im1 Do Q');
    this.newPage();
  }
}

function build(renderer, fonts, outPath, meta) {
  const objs = [{}, {}];
  let next = 3;
  const reserve = () => { const id = next++; objs[id - 1] = {}; return id; };
  const put = (id, body, stream) => { objs[id - 1] = { id, body, stream }; };
  const addFont = function (font, isBold) {
    const fdesc = reserve(), ffile = reserve(), toun = reserve(), fid = reserve();
    const fbuf = zlib.deflateSync(font.t.buf, { level: 9 });
    const bb = font.t.bbox.map((v) => Math.round(v * font.k)).join(' ');
    const asc = Math.round(font.t.asc * font.k), desc = Math.round(font.t.desc * font.k);
    put(fdesc, '<< /Type /FontDescriptor /FontName /' + font.name + ' /Flags ' + (isBold ? 262176 : 32) +
      ' /FontBBox [' + bb + '] /ItalicAngle 0 /Ascent ' + asc + ' /Descent ' + desc +
      ' /CapHeight ' + asc + ' /StemV ' + (isBold ? 130 : 80) + ' /FontFile2 ' + ffile + ' 0 R >>');
    put(ffile, '<< /Length ' + fbuf.length + ' /Length1 ' + font.t.buf.length + ' /Filter /FlateDecode >>', fbuf);
    let cm = '/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n';
    cm += '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n';
    cm += '/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<00> <FF>\nendcodespacerange\n';
    const entries = [];
    for (let c = 32; c <= 255; c++) {
      const cp = REV.get(c) || c;
      entries.push('<' + c.toString(16).padStart(2, '0') + '> <' + cp.toString(16).padStart(4, '0') + '>');
    }
    for (let i = 0; i < entries.length; i += 100) {
      const part = entries.slice(i, i + 100);
      cm += part.length + ' beginbfchar\n' + part.join('\n') + '\nendbfchar\n';
    }
    cm += 'endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n';
    const cmz = zlib.deflateSync(Buffer.from(cm, 'latin1'), { level: 9 });
    put(toun, '<< /Length ' + cmz.length + ' /Filter /FlateDecode >>', cmz);
    put(fid, '<< /Type /Font /Subtype /TrueType /BaseFont /' + font.name + ' /FirstChar 32 /LastChar 255 /Widths [' +
      font.widths.join(' ') + '] /FontDescriptor ' + fdesc + ' 0 R /Encoding /WinAnsiEncoding /ToUnicode ' + toun + ' 0 R >>');
    return fid;
  };
  const ids = { F1: addFont(fonts.F1, false), F2: addFont(fonts.F2, true), F3: addFont(fonts.F3, false) };
  const pageIds = [], contentIds = [];
  let imgId = null;
  for (const pg of renderer.pages) {
    if (pg.image) {
      imgId = reserve();
      put(imgId, '<< /Type /XObject /Subtype /Image /Width ' + pg.image.w + ' /Height ' + pg.image.h +
        ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length ' + pg.image.data.length + ' >>', pg.image.data);
    }
    const cz = zlib.deflateSync(Buffer.from(pg.ops.join('\n'), 'latin1'), { level: 9 });
    const cid = reserve();
    put(cid, '<< /Length ' + cz.length + ' /Filter /FlateDecode >>', cz);
    contentIds.push(cid);
  }
  let k = 0;
  for (const pg of renderer.pages) {
    const pid = reserve();
    const xo = pg.image ? '/Im1 ' + imgId + ' 0 R' : '';
    put(pid, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + num(pg.w) + ' ' + num(pg.h) + '] ' +
      '/Resources << /Font << /F1 ' + ids.F1 + ' 0 R /F2 ' + ids.F2 + ' 0 R /F3 ' + ids.F3 + ' 0 R >> ' +
      '/XObject << ' + xo + ' >> /ProcSet [/PDF /Text /ImageC] >> /Contents ' + contentIds[k] + ' 0 R >>');
    k++;
    pageIds.push(pid);
  }
  put(2, '<< /Type /Pages /Count ' + pageIds.length + ' /Kids [' + pageIds.map((i) => i + ' 0 R').join(' ') + '] >>');
  put(1, '<< /Type /Catalog /Pages 2 0 R >>');
  const infoId = reserve();
  const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  put(infoId, '<< /Title (' + esc(sanitize(meta.title)) + ')' +
    (meta.author ? ' /Author (' + esc(sanitize(meta.author)) + ')' : '') +
    ' /Subject (' + esc(sanitize(meta.subject || '')) + ') /Creator (md2pdf.mjs) /Producer (md2pdf.mjs)' +
    ' /CreationDate (D:' + stamp + 'Z) >>');
  const chunks = [Buffer.from('%PDF-1.5\n%\xE2\xE3\xCF\xD3\n', 'latin1')];
  let off = chunks[0].length;
  const offs = [];
  for (const o of objs) {
    offs.push(off);
    const head = Buffer.from(o.id + ' 0 obj\n' + o.body + '\n', 'latin1');
    const parts = [head];
    if (o.stream) parts.push(Buffer.from('stream\n', 'latin1'), o.stream, Buffer.from('\nendstream', 'latin1'));
    parts.push(Buffer.from('\nendobj\n', 'latin1'));
    const b = Buffer.concat(parts);
    chunks.push(b); off += b.length;
  }
  const xref = off;
  let x = 'xref\n0 ' + (objs.length + 1) + '\n0000000000 65535 f \n';
  for (const o of offs) x += String(o).padStart(10, '0') + ' 00000 n \n';
  x += 'trailer\n<< /Size ' + (objs.length + 1) + ' /Root 1 0 R /Info ' + infoId + ' 0 R >>\nstartxref\n' + xref + '\n%%EOF\n';
  chunks.push(Buffer.from(x, 'latin1'));
  fs.writeFileSync(outPath, Buffer.concat(chunks));
}

function decorate(r, meta) {
  const total = r.pages.length;
  r.pages.forEach((pg, i) => {
    if (pg.bare) return;
    r.cur = pg;
    r.text(M.l, 46, meta.headLeft, 'F1', 7.4, COL.muted);
    const right = meta.headRight;
    r.text(pg.w - M.r - r.f.F1.w(right, 7.4), 46, right, 'F1', 7.4, COL.muted);
    r.line(M.l, 52, pg.w - M.r, 52, COL.rule, 0.6);
    r.line(M.l, pg.h - 34, pg.w - M.r, pg.h - 34, COL.rule, 0.6);
    r.text(M.l, pg.h - 23, meta.foot, 'F1', 7.2, COL.soft);
    const pn = (i + 1) + '/' + total;
    r.text(pg.w - M.r - r.f.F1.w(pn, 7.2), pg.h - 23, pn, 'F1', 7.2, COL.soft);
  });
}

function tableUnderHeading(blocks, prefix) {
  let seen = false;
  for (const b of blocks) {
    if (b.t === 'h' && b.text.indexOf(prefix) === 0) { seen = true; continue; }
    if (seen && b.t === 'table') return b.rows;
    if (seen && b.t === 'h') return null;
  }
  return null;
}

const argv = process.argv.slice(2);
const inPath = argv[0], outPath = argv[1];
const flag = function (name) { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
const svgPath = flag('--svg');
const footNote = flag('--footer') || 'Weitergabefassung';
const author = flag('--author') || '';
const headRight = flag('--head-right') || '';
const md = fs.readFileSync(inPath, 'utf8');
const blocks = loadDoc(md);

const fonts = {
  F1: new Font(fontPath('Lato-Regular.ttf'), 'Lato-Regular'),
  F2: new Font(fontPath('Lato-Bold.ttf'), 'Lato-Bold'),
  F3: new Font(fontPath('IBMPlexMono-Regular.ttf'), 'IBMPlexMono-Regular'),
};
const r = new Renderer(fonts);
const titleBlock = blocks.find((b) => b.t === 'h' && b.lvl === 1);

for (const b of blocks) {
  if (b.t === 'h') r.heading(b.lvl, b.text);
  else if (b.t === 'p') r.paragraph(b.text);
  else if (b.t === 'list') r.list(b.items);
  else if (b.t === 'quote') r.quote(b.lines);
  else if (b.t === 'table') r.table(b.rows);
  else if (b.t === 'code') r.code(b.lines);
  else if (b.t === 'hr') { r.ensure(10); r.line(M.l, r.y + 2, PAGE.w - M.r, r.y + 2, COL.rule, 0.8); r.y += 10; }
  else if (b.t === 'marker') {
    if (b.name === 'GRAFIK' && svgPath) {
      r.imagePage(fs.readFileSync(svgPath, 'utf8'));
    } else if (b.name === 'LAYOUT') {
      const rows = tableUnderHeading(blocks, '1. Betriebsmittel');
      if (rows) {
        r.paragraph('**Schrankansicht (Zuordnung nach Abschnitt 1):**');
        r.table([['BMK', 'Ort', 'Betriebsmittel']].concat(rows.slice(1).map((row) => [row[0], row[2], row[1]])));
      }
    } else if (b.name === 'WIRING') {
      const rows = tableUnderHeading(blocks, '5. Aderliste');
      if (rows) r.table([['Nr.', 'Von', 'Nach']].concat(rows.slice(1).map((row) => [row[0], row[2], row[3]])));
    }
  }
}

decorate(r, {
  headLeft: (titleBlock ? titleBlock.text : 'Dokument').slice(0, 74),
  headRight,
  foot: footNote,
});
build(r, fonts, outPath, {
  title: titleBlock ? titleBlock.text : 'Dokument',
  subject: footNote,
  author,
});
if (r.overflows) { console.log('OVERFLOW ' + r.overflows.length); r.overflows.slice(0, 12).forEach((o) => console.log('  ' + o)); }
console.log('pdf ' + outPath + '  pages=' + r.pages.length + '  ' + (fs.statSync(outPath).size / 1024).toFixed(0) + ' kB');
