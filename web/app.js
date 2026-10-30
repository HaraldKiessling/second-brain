// Einstellungsseite des Second Brain. Spricht direkt mit der GitHub-API;
// der Token bleibt im localStorage dieses Browsers.

'use strict';

// Bekannte Zugangsdaten. Namen muessen zu den Workflows im Daten-Repo passen.
const SECRETS = [
  { name: 'MAIL_GMX_USER', wofuer: 'GMX: Mail-Adresse' },
  { name: 'MAIL_GMX_PASSWORD', wofuer: 'GMX: App-Passwort für IMAP' },
  { name: 'MAIL_GMAIL_USER', wofuer: 'Gmail: Mail-Adresse' },
  { name: 'MAIL_GMAIL_PASSWORD', wofuer: 'Gmail: App-Passwort (Google-Konto → Sicherheit → App-Passwörter)' },
  { name: 'OPENROUTER_API_KEY', wofuer: 'KI-Einordnen (optional, einschalten in config/einordnen.yaml)' },
];
const REGEL_DATEI = 'regeln/mail.json';
const VORSCHLAG_DATEI = 'regeln/mail-vorschlaege.json';
const MAIL_WORKFLOW = 'mail.yml';

const $ = (sel) => document.querySelector(sel);
const zustand = { repo: '', token: '', themen: {}, personen: {}, regeln: null, regelSha: '', bearbeitet: -1, regelVonMail: null, regelVonVorschlag: null };

// --- Speicher (localStorage kann fehlen, z. B. im privaten Modus) ----------

function lade(schluessel) {
  try { return localStorage.getItem(schluessel) || ''; } catch { return ''; }
}
function merke(schluessel, wert) {
  try { wert ? localStorage.setItem(schluessel, wert) : localStorage.removeItem(schluessel); } catch { /* egal */ }
}

// --- GitHub-API -------------------------------------------------------------

async function gh(pfad, optionen = {}) {
  const antwort = await fetch('https://api.github.com' + pfad, {
    ...optionen,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: 'Bearer ' + zustand.token,
      'X-GitHub-Api-Version': '2022-11-28',
      ...(optionen.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  if (!antwort.ok) {
    let text = '';
    try { text = (await antwort.json()).message || ''; } catch { /* kein JSON */ }
    throw new Error(`GitHub ${antwort.status}: ${text || antwort.statusText}`);
  }
  // Secrets anlegen liefert 201 ohne Inhalt, aendern 204.
  const text = await antwort.text();
  return text ? JSON.parse(text) : null;
}

const b64zuText = (b64) => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\n/g, '')), (c) => c.charCodeAt(0)));
const textZuB64 = (text) => btoa(String.fromCharCode(...new TextEncoder().encode(text)));

async function dateiLesen(pfad) {
  const d = await gh(`/repos/${zustand.repo}/contents/${encodeURI(pfad)}`);
  return { text: b64zuText(d.content), sha: d.sha };
}

async function dateiSchreiben(pfad, text, sha, nachricht) {
  const d = await gh(`/repos/${zustand.repo}/contents/${encodeURI(pfad)}`, {
    method: 'PUT',
    body: JSON.stringify({ message: nachricht, content: textZuB64(text), sha }),
  });
  return d.content.sha;
}

// Mehrere Dateien in einem Commit schreiben oder loeschen (Git-Data-API).
// aenderungen: [{ pfad, text }] oder [{ pfad, loeschen: true }]. Laeuft
// parallel ein Ablauf, wird mit dem neuen Stand bis zu dreimal wiederholt.
async function commitMehrere(erzeugen, nachricht) {
  const basis = `/repos/${zustand.repo}/git`;
  for (let versuch = 1; ; versuch++) {
    const ref = await gh(`${basis}/ref/heads/main`);
    const kopf = await gh(`${basis}/commits/${ref.object.sha}`);
    const aenderungen = await erzeugen();
    const baum = await gh(`${basis}/trees`, {
      method: 'POST',
      body: JSON.stringify({
        base_tree: kopf.tree.sha,
        tree: aenderungen.map((a) => (a.loeschen
          ? { path: a.pfad, mode: '100644', type: 'blob', sha: null }
          : { path: a.pfad, mode: '100644', type: 'blob', content: a.text })),
      }),
    });
    const commit = await gh(`${basis}/commits`, {
      method: 'POST',
      body: JSON.stringify({ message: nachricht, tree: baum.sha, parents: [kopf.sha] }),
    });
    try {
      await gh(`${basis}/refs/heads/main`, { method: 'PATCH', body: JSON.stringify({ sha: commit.sha }) });
      return;
    } catch (e) {
      if (versuch >= 3) throw e;
    }
  }
}

async function dateiOderLeer(pfad) {
  try { return (await dateiLesen(pfad)).text; } catch (e) {
    if (e.message.startsWith('GitHub 404')) return '';
    throw e;
  }
}

async function secretSetzen(name, wert) {
  await sodium.ready;
  const schluessel = await gh(`/repos/${zustand.repo}/actions/secrets/public-key`);
  const verschluesselt = sodium.crypto_box_seal(
    sodium.from_string(wert),
    sodium.from_base64(schluessel.key, sodium.base64_variants.ORIGINAL));
  await gh(`/repos/${zustand.repo}/actions/secrets/${name}`, {
    method: 'PUT',
    body: JSON.stringify({
      encrypted_value: sodium.to_base64(verschluesselt, sodium.base64_variants.ORIGINAL),
      key_id: schluessel.key_id,
    }),
  });
}

// --- Oberflaeche ------------------------------------------------------------

function melde(text, art = '') {
  const m = $('#meldung');
  m.textContent = text;
  m.className = art;
}

function zeigeReiter(name) {
  document.querySelectorAll('.reiter').forEach((s) => { s.hidden = s.id !== name; });
  document.querySelectorAll('#reiter button').forEach((b) => b.classList.toggle('aktiv', b.dataset.reiter === name));
  merke('sb-reiter', name);
  return ({ uebersicht: zeigeUebersicht, eingang: zeigeEingang, zugang: zeigeSecrets, regeln: zeigeRegeln, dateien: zeigeDatei, ablaeufe: zeigeLaeufe })[name]();
}

function zelle(zeile, text, klasse) {
  const td = zeile.insertCell();
  // Spaltenname fuer die Kartenansicht auf schmalen Bildschirmen (style.css)
  const th = zeile.closest('table').querySelectorAll('th')[td.cellIndex];
  if (th && th.textContent) td.dataset.label = th.textContent;
  td.textContent = text;
  if (klasse) td.className = klasse;
  return td;
}

function knopf(text, beiKlick, klasse = 'klein') {
  const b = document.createElement('button');
  b.textContent = text;
  b.className = klasse;
  b.addEventListener('click', beiKlick);
  return b;
}

// Zugangsdaten

async function zeigeSecrets() {
  const tbody = $('#secrets');
  tbody.textContent = '';
  let vorhanden = [];
  try {
    vorhanden = (await gh(`/repos/${zustand.repo}/actions/secrets?per_page=100`)).secrets;
  } catch (e) { melde(e.message, 'fehler'); return; }
  const gesetzt = new Map(vorhanden.map((s) => [s.name, s.updated_at]));
  const liste = [...SECRETS, ...vorhanden.filter((s) => !SECRETS.some((b) => b.name === s.name)).map((s) => ({ name: s.name, wofuer: '' }))];
  for (const s of liste) {
    const z = tbody.insertRow();
    zelle(z, s.name);
    zelle(z, s.wofuer, 'hinweis');
    const stand = gesetzt.get(s.name);
    zelle(z, stand ? 'gesetzt ' + new Date(stand).toLocaleDateString('de-DE') : 'fehlt', stand ? 'gut' : 'warn');
    z.insertCell().append(knopf(stand ? 'Ändern' : 'Setzen', () => secretAbfragen(s.name)));
  }
}

async function secretAbfragen(name) {
  const wert = prompt(`Neuer Wert für ${name}:`);
  if (!wert) return;
  try {
    melde('Speichere ' + name + ' …');
    await secretSetzen(name, wert);
    melde(name + ' gespeichert.', 'gut');
    zeigeSecrets();
  } catch (e) { melde(e.message, 'fehler'); }
}

// Eingang

// Frontmatter wie in src/second_brain/notiz.py. CORE_SCHEMA laesst Datumswerte
// als Text stehen und schreibt sie ohne Anfuehrungszeichen, so dass Python sie
// wieder als Datum liest.
const PFLICHTFELDER = ['id', 'erstellt', 'quelle', 'personen', 'themen'];

function notizLesen(inhalt) {
  const ende = inhalt.indexOf('\n---', 4);
  if (!inhalt.startsWith('---\n') || ende < 0) throw new Error('kein Frontmatter');
  return { meta: jsyaml.load(inhalt.slice(4, ende), { schema: jsyaml.CORE_SCHEMA }) || {},
    text: inhalt.slice(ende + 4).replace(/^\n+/, '') };
}

function notizSchreiben(meta, text) {
  const reihenfolge = [...PFLICHTFELDER, ...Object.keys(meta).filter((k) => !PFLICHTFELDER.includes(k)).sort()];
  const geordnet = {};
  for (const k of reihenfolge) if (k in meta) geordnet[k] = meta[k];
  const kopf = jsyaml.dump(geordnet, { schema: jsyaml.CORE_SCHEMA, flowLevel: 1, lineWidth: -1 }).trim();
  return `---\n${kopf}\n---\n\n${text.replace(/\n+$/, '')}\n`;
}

function jahrOrdner(datum) {
  const jahr = Number(datum.slice(0, 4));
  return jahr === new Date().getFullYear() ? `0-${jahr}` : String(jahr);
}

function unterordnerEinsetzen(uo, datum) {
  return (uo || '').replaceAll('{jahr}', datum.slice(0, 4)).replaceAll('{monat}', datum.slice(5, 7)).replace(/^\/+|\/+$/g, '');
}

function unterordnerGueltig(uo) {
  return !uo || uo.split('/').every((t) => t.trim() && t !== '.' && t !== '..' && !t.includes('\\'));
}

function absenderAdresse(e) {
  if (e.meta.absender) return String(e.meta.absender);
  const von = /^Von: (.+?)\s*$/m.exec(e.text);
  const a = von ? (/<([^>]+)>/.exec(von[1]) || [, von[1]])[1] : '';
  return a.trim().toLowerCase();
}

const titelVon = (text) => ((/^# (.+)$/m.exec(text) || [])[1] || '(ohne Betreff)').trim();

function protokollZeile(alt, datum, wer, aenderung) {
  const monat = datum.slice(0, 7);
  const kopf = alt || `# Änderungsprotokoll ${monat}\n\n| Datum | Wer | Änderung |\n| --- | --- | --- |\n`;
  return kopf.replace(/\n*$/, '\n') + `| ${datum} | ${wer} | ${aenderung} |\n`;
}

async function eingangLaden() {
  let dateien = [];
  try { dateien = await gh(`/repos/${zustand.repo}/contents/eingang`); } catch (e) {
    if (!e.message.startsWith('GitHub 404')) throw e;
  }
  const md = dateien.filter((d) => d.type === 'file' && d.name.endsWith('.md') && d.name !== 'README.md');
  const eintraege = await Promise.all(md.map(async (d) => {
    const { text } = await dateiLesen(d.path);
    try { return { pfad: d.path, ...notizLesen(text) }; } catch { return null; }
  }));
  return eintraege.filter(Boolean).sort((a, b) => String(b.meta.erstellt).localeCompare(String(a.meta.erstellt)));
}

async function zeigeEingang() {
  const liste = $('#eingang-liste');
  liste.textContent = 'Lade …';
  let eintraege;
  try {
    await stammdatenLaden();
    if (!zustand.regeln) {
      const d = await dateiLesen(REGEL_DATEI);
      zustand.regeln = JSON.parse(d.text);
      zustand.regelSha = d.sha;
    }
    eintraege = await eingangLaden();
  } catch (e) { liste.textContent = ''; melde(e.message, 'fehler'); return; }
  liste.textContent = '';
  if (!eintraege.length) {
    const p = document.createElement('p');
    p.className = 'gut';
    p.textContent = 'Nichts offen. Alles eingeordnet.';
    liste.append(p);
  }
  for (const e of eintraege) liste.append(eingangKarte(e));
  zeigeVerworfen();
}

function auswahlFelder(vorgabe) {
  const box = document.createElement('div');
  const reihe = document.createElement('div');
  reihe.className = 'reihe';
  const thema = document.createElement('select');
  thema.add(new Option('– Thema wählen –', ''));
  for (const [k, t] of Object.entries(zustand.themen)) thema.add(new Option(t.name || k, k, false, k === vorgabe.thema));
  const uo = document.createElement('input');
  uo.value = vorgabe.unterordner || '';
  uo.placeholder = 'z. B. firma/rechnungen/{jahr}';
  const l1 = document.createElement('label'); l1.append('Thema', thema);
  const l2 = document.createElement('label'); l2.append('Unterordner', uo);
  reihe.append(l1, l2);
  const personen = document.createElement('fieldset');
  personen.innerHTML = '<legend>Personen</legend>';
  const aktiv = vorgabe.personen && vorgabe.personen.length ? vorgabe.personen : (zustand.regeln.standard_personen || []);
  for (const [k, p] of Object.entries(zustand.personen)) {
    const l = document.createElement('label');
    const c = document.createElement('input');
    c.type = 'checkbox'; c.value = k; c.checked = aktiv.includes(k);
    l.append(c, ' ' + (p.name || k));
    personen.append(l);
  }
  box.append(reihe, personen);
  box.wert = () => ({
    thema: thema.value,
    unterordner: uo.value.trim(),
    personen: [...personen.querySelectorAll('input:checked')].map((c) => c.value),
  });
  box.setzen = (v) => {
    thema.value = v.thema || '';
    uo.value = v.unterordner || '';
    if (v.personen && v.personen.length) {
      personen.querySelectorAll('input').forEach((c) => { c.checked = v.personen.includes(c.value); });
    }
  };
  return box;
}

function eingangKarte(e) {
  const karte = document.createElement('div');
  karte.className = 'karte';
  const h = document.createElement('h3');
  h.textContent = titelVon(e.text);
  const info = document.createElement('div');
  info.className = 'hinweis';
  info.textContent = `${e.meta.erstellt} · ${absenderAdresse(e) || 'unbekannt'} · ${e.meta.quelle}`;
  karte.append(h, info);

  const v = e.meta.vorschlag;
  const vb = document.createElement('div');
  vb.className = 'vorschlag';
  if (v && v.thema) {
    const k = Math.round((v.konfidenz || 0) * 100);
    const t = (zustand.themen[v.thema] || {}).name || v.thema;
    vb.innerHTML = '<span class="konfidenz"></span> <span class="was"></span><div class="hinweis grund"></div>';
    vb.querySelector('.konfidenz').textContent = `Vorschlag (${k} %):`;
    vb.querySelector('.was').textContent = [t, v.unterordner].filter(Boolean).join(' / ') + ` · ${(v.personen || []).join(', ')}`;
    vb.querySelector('.grund').textContent = v.grund || '';
  } else {
    vb.textContent = 'Kein Vorschlag. ' + (e.meta.offen_grund || '');
  }
  karte.append(vb);

  const felder = auswahlFelder(v || {});
  const alternativen = (v && v.alternativen) || [];
  if (alternativen.length) {
    const wahl = document.createElement('div');
    wahl.className = 'hinweis';
    wahl.append('Mögliche Ordner: ');
    for (const a of [v, ...alternativen]) {
      const t = (zustand.themen[a.thema] || {}).name || a.thema;
      wahl.append(knopf(`${[t, a.unterordner].filter(Boolean).join(' / ')} (${Math.round((a.konfidenz || 0) * 100)} %)`,
        () => felder.setzen(a), 'klein leise'));
    }
    vb.append(wahl);
  }
  const fehler = document.createElement('p');
  fehler.className = 'fehler';
  const tun = (fn) => async () => {
    fehler.textContent = '';
    karte.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    try { await fn(); } catch (err) { fehler.textContent = err.message; }
    karte.querySelectorAll('button').forEach((b) => { b.disabled = false; });
  };
  const knoepfe = document.createElement('div');
  knoepfe.append(
    knopf(v && v.thema ? 'Übernehmen' : 'Ablegen', tun(async () => {
      const w = felder.wert();
      const f = auswahlPruefen(w);
      if (f) { fehler.textContent = f; return; }
      await eingangAblegen(e, w, 'manuell');
      karte.remove();
    }), ''),
    knopf('Regel aus dieser Mail', () => regelAusMail(e, felder.wert()), 'leise'),
    knopf('Nur Index', tun(async () => { await eingangVerwerfen(e, false); karte.remove(); }), 'leise'),
    knopf('Spam', tun(async () => { await eingangVerwerfen(e, true); karte.remove(); }), 'leise'),
  );
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = 'Mail anzeigen';
  const pre = document.createElement('pre');
  pre.textContent = e.text.replace(/^# .*\n+/, '');
  details.append(summary, pre);
  karte.append(felder, knoepfe, fehler, details);
  return karte;
}

function auswahlPruefen(w) {
  if (!(w.thema in zustand.themen)) return 'Bitte ein Thema wählen.';
  if (!w.personen.length) return 'Mindestens eine Person wählen.';
  if (!unterordnerGueltig(w.unterordner)) return 'Unterordner ungültig (keine leeren Teile, kein ..).';
  return '';
}

// Eingang -> Notiz unter notizen/<jahr>/<thema>/, mit Protokollzeile, ein Commit.
async function eingangAblegen(e, w, durch, wie = 'aus Eingang abgelegt') {
  const meta = { ...e.meta };
  const datum = String(meta.erstellt);
  delete meta.offen_grund;
  delete meta.vorschlag;
  delete meta.konfidenz;
  const thema = zustand.themen[w.thema] || {};
  meta.themen = [w.thema];
  meta.personen = w.personen;
  meta.ablage = [jahrOrdner(datum), thema.ablage, unterordnerEinsetzen(w.unterordner, datum)].filter(Boolean).join('/');
  meta.eingeordnet_durch = durch;
  if (!meta.absender && absenderAdresse(e)) meta.absender = absenderAdresse(e);
  const ziel = `notizen/${datum.slice(0, 4)}/${w.thema}/${meta.id}.md`;
  const heute = new Date().toISOString().slice(0, 10);
  const protokoll = `protokoll/${heute.slice(0, 7)}.md`;
  await commitMehrere(async () => [
    { pfad: ziel, text: notizSchreiben(meta, e.text) },
    ...(ziel !== e.pfad ? [{ pfad: e.pfad, loeschen: true }] : []),
    { pfad: protokoll, text: protokollZeile(await dateiOderLeer(protokoll), heute, durch, `Notiz \`${meta.id}\` ${wie}`) },
  ], `${e.pfad.startsWith('eingang/') ? 'eingang' : 'korrektur'}: ${meta.id} -> ${w.thema} (Web)`);
  melde(`Abgelegt unter ${meta.ablage}.`, 'gut');
  return ziel;
}

// Uebersicht: Ablaeufe und automatisch abgelegte Notizen mit Korrektur

function unterordnerAusAblage(ablage, thema) {
  const teile = String(ablage || '').split('/').filter(Boolean);
  const t = zustand.themen[thema] || {};
  return teile.length > 2 && teile[1] === t.ablage ? teile.slice(2).join('/') : '';
}

async function laeufeLaden() {
  const monate = [0, 1].map((n) => { const d = new Date(); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - n); return d.toISOString().slice(0, 7); });
  const texte = await Promise.all(monate.map((m) => dateiOderLeer(`protokoll/laeufe/${m}.jsonl`).catch(() => '')));
  return texte.join('\n').split('\n').filter(Boolean)
    .map((z) => { try { return JSON.parse(z); } catch { return null; } })
    .filter(Boolean).sort((a, b) => b.zeit.localeCompare(a.zeit));
}

async function zeigeUebersicht() {
  const status = $('#ablauf-status');
  const tbody = $('#lauf-liste');
  const liste = $('#auto-liste');
  tbody.textContent = ''; liste.textContent = 'Lade …'; status.textContent = '';
  let laeufe;
  try {
    await stammdatenLaden();
    if (!zustand.regeln) zustand.regeln = JSON.parse((await dateiLesen(REGEL_DATEI)).text);
    laeufe = await laeufeLaden();
    const d = await gh(`/repos/${zustand.repo}/actions/workflows/${MAIL_WORKFLOW}/runs?per_page=1`);
    const l = d.workflow_runs[0];
    if (l) {
      const [text, klasse] = ERGEBNIS[l.conclusion] || [STATUS[l.status] || l.status, ''];
      status.textContent = `Letzter Abruf: ${new Date(l.created_at).toLocaleString('de-DE')}, ${text}.`;
      status.className = klasse;
    }
  } catch (e) { liste.textContent = ''; melde(e.message, 'fehler'); return; }
  for (const l of laeufe.slice(0, 15)) {
    const z = tbody.insertRow();
    zelle(z, new Date(l.zeit).toLocaleString('de-DE'));
    zelle(z, l.konto);
    zelle(z, `${l.notiz} Notizen, ${l.offen} Eingang, ${l.index} Index, ${l.verwerfen} verworfen`);
  }
  if (!laeufe.length) zelle(tbody.insertRow(), 'Noch keine Abrufe mit neuen Mails.', 'hinweis');
  liste.textContent = '';
  const auto = laeufe.flatMap((l) => (l.eintraege || []).filter((e) => e.aktion === 'notiz' && e.durch !== 'manuell')).slice(0, 30);
  if (!auto.length) { liste.textContent = 'Noch nichts automatisch abgelegt.'; liste.className = 'hinweis'; }
  for (const a of auto) liste.append(autoKarte(a));
}

function autoKarte(a) {
  const karte = document.createElement('div');
  karte.className = 'karte';
  const h = document.createElement('h3');
  h.textContent = a.titel || '(ohne Betreff)';
  const info = document.createElement('div');
  info.className = 'hinweis';
  const t = (zustand.themen[a.thema] || {}).name || a.thema;
  info.textContent = `${a.absender} · ${t} · ${a.durch}${a.konfidenz < 1 ? ` (${Math.round(a.konfidenz * 100)} %)` : ''}`;
  const fehler = document.createElement('p');
  fehler.className = 'fehler';
  karte.append(h, info);
  karte.append(knopf('Korrigieren', async (ev) => {
    ev.target.remove();
    let e;
    try {
      const { text } = await dateiLesen(a.pfad);
      e = { pfad: a.pfad, ...notizLesen(text) };
    } catch {
      fehler.textContent = 'Notiz wurde inzwischen verschoben oder gelöscht.';
      return;
    }
    const thema = (e.meta.themen || [])[0];
    const felder = auswahlFelder({ thema, unterordner: unterordnerAusAblage(e.meta.ablage, thema), personen: e.meta.personen });
    const ablage = document.createElement('div');
    ablage.className = 'hinweis';
    ablage.textContent = 'Jetzt: ' + (e.meta.ablage || '');
    karte.insertBefore(ablage, fehler);
    karte.insertBefore(felder, fehler);
    karte.insertBefore(knopf('Speichern', async () => {
      const w = felder.wert();
      const f = auswahlPruefen(w);
      if (f) { fehler.textContent = f; return; }
      try {
        a.pfad = await eingangAblegen(e, w, 'manuell', 'korrigiert');
        ablage.textContent = 'Jetzt: ' + [jahrOrdner(String(e.meta.erstellt)), (zustand.themen[w.thema] || {}).ablage, unterordnerEinsetzen(w.unterordner, String(e.meta.erstellt))].filter(Boolean).join('/');
        felder.remove();
      } catch (err) { fehler.textContent = err.message; }
    }, ''), fehler);
  }, 'klein leise'), fehler);
  return karte;
}

// Eingang -> Indexeintrag; bei Spam zusaetzlich Absender in die Verwerfen-Liste.
async function eingangVerwerfen(e, spam) {
  const adresse = absenderAdresse(e);
  const datum = String(e.meta.erstellt);
  const index = `index/mail/${datum.slice(0, 7)}.jsonl`;
  const kurz = e.text.replace(/^# .*\n+/, '').replace(/^(Von|Datum|Anhänge): .*$/gm, '').split(/\s+/).join(' ').trim().slice(0, 300);
  const zeile = { datum, konto: e.meta.quelle, absender: adresse, betreff: titelVon(e.text), kurz, message_id: e.meta.message_id || '' };
  if (spam) zeile.verworfen = 'manuell: Spam';
  await commitMehrere(async () => {
    const aenderungen = [
      { pfad: index, text: (await dateiOderLeer(index)) + JSON.stringify(zeile) + '\n' },
      { pfad: e.pfad, loeschen: true },
    ];
    if (spam && adresse) {
      const regeln = JSON.parse((await dateiLesen(REGEL_DATEI)).text);
      if (!regeln.verwerfen.includes(adresse)) regeln.verwerfen.push(adresse);
      aenderungen.push({ pfad: REGEL_DATEI, text: JSON.stringify(regeln, null, 2) + '\n' });
      zustand.regeln = null;
    }
    return aenderungen;
  }, `eingang: ${e.meta.id} ${spam ? 'als Spam verworfen' : 'nur Index'} (Web)`);
  melde(spam ? `Verworfen; künftige Mails von ${adresse} werden aussortiert.` : 'In den Index verschoben.', 'gut');
}

async function regelAusMail(e, w) {
  const adresse = absenderAdresse(e);
  const domain = adresse.split('@')[1] || adresse;
  const name = domain.split('.').slice(-2, -1)[0] || domain;
  await zeigeReiter('regeln');
  zustand.regelVonMail = e;
  zustand.regelVonVorschlag = null;
  regelFormular(-1, { name, absender: [domain], thema: w.thema, unterordner: w.unterordner, personen: w.personen });
  $('#regel-form-titel').textContent = `Neue Regel aus Mail „${titelVon(e.text)}“`;
  melde('Prüfe die Regel. Beim Speichern wird auch diese Mail abgelegt.');
}

async function zeigeVerworfen() {
  const tbody = $('#verworfen-liste');
  tbody.textContent = '';
  const monat = new Date().toISOString().slice(0, 7);
  const text = await dateiOderLeer(`index/mail/${monat}.jsonl`).catch(() => '');
  const zeilen = text.split('\n').filter(Boolean).map((z) => { try { return JSON.parse(z); } catch { return null; } })
    .filter((z) => z && z.verworfen).reverse().slice(0, 30);
  for (const z of zeilen) {
    const r = tbody.insertRow();
    zelle(r, z.datum); zelle(r, z.absender); zelle(r, z.betreff); zelle(r, z.verworfen, 'hinweis');
  }
  if (!zeilen.length) zelle(tbody.insertRow(), 'Nichts verworfen.', 'hinweis');
}

// Regeln

async function stammdatenLaden() {
  const [themen, personen] = await Promise.all([dateiLesen('config/themen.yaml'), dateiLesen('config/personen.yaml')]);
  zustand.themen = jsyaml.load(themen.text).themen || {};
  zustand.personen = jsyaml.load(personen.text).personen || {};
}

async function zeigeRegeln() {
  try {
    await stammdatenLaden();
    const d = await dateiLesen(REGEL_DATEI);
    zustand.regeln = JSON.parse(d.text);
    zustand.regelSha = d.sha;
  } catch (e) { melde(e.message, 'fehler'); return; }
  const tbody = $('#regel-liste');
  tbody.textContent = '';
  zustand.regeln.regeln.forEach((r, i) => {
    const z = tbody.insertRow();
    zelle(z, r.name);
    zelle(z, (r.absender || []).join(', '));
    zelle(z, (r.empfaenger || []).join(', '));
    zelle(z, (r.betreff || []).join(', '));
    zelle(z, (zustand.themen[r.thema] || {}).name || r.thema);
    zelle(z, (r.personen || zustand.regeln.standard_personen || []).join(', '));
    const td = z.insertCell();
    td.append(knopf('Ändern', () => regelFormular(i)), knopf('Löschen', () => regelLoeschen(i), 'klein leise'));
  });
  $('#verwerfen').value = (zustand.regeln.verwerfen || []).join('\n');
  $('#regel-form').hidden = true;
  await zeigeVorschlaege();
}

async function zeigeVorschlaege() {
  const text = await dateiOderLeer(VORSCHLAG_DATEI).catch(() => '');
  const daten = text ? JSON.parse(text) : { vorschlaege: [] };
  const tbody = $('#vorschlag-liste');
  tbody.textContent = '';
  $('#vorschlag-bereich').hidden = !daten.vorschlaege.length;
  for (const v of daten.vorschlaege) {
    const z = tbody.insertRow();
    zelle(z, v.absender.join(', '));
    zelle(z, (zustand.themen[v.thema] || {}).name || v.thema);
    zelle(z, v.unterordner || '');
    zelle(z, v.grund, 'hinweis');
    z.insertCell().append(
      knopf('Übernehmen', () => {
        regelFormular(-1, v);
        zustand.regelVonMail = null;
        zustand.regelVonVorschlag = v;
      }),
      knopf('Ablehnen', () => vorschlagErledigt(v, true), 'klein leise'));
  }
}

// Vorschlag aus der Liste nehmen; abgelehnte Domains merkt sich der Ablauf.
async function vorschlagErledigt(v, abgelehnt) {
  try {
    const d = await dateiLesen(VORSCHLAG_DATEI);
    const daten = JSON.parse(d.text);
    daten.vorschlaege = daten.vorschlaege.filter((x) => x.absender.join() !== v.absender.join());
    if (abgelehnt) daten.abgelehnt = [...new Set([...(daten.abgelehnt || []), ...v.absender])];
    await dateiSchreiben(VORSCHLAG_DATEI, JSON.stringify(daten, null, 2) + '\n', d.sha,
      `regeln: Vorschlag ${v.name} ${abgelehnt ? 'abgelehnt' : 'übernommen'} (Web)`);
    if (abgelehnt) melde(`Vorschlag ${v.name} abgelehnt.`, 'gut');
    await zeigeVorschlaege();
  } catch (e) { melde(e.message, 'fehler'); }
}

function regelFormular(index, vorlage) {
  const f = $('#regel-form');
  const r = index >= 0 ? zustand.regeln.regeln[index] : (vorlage || { personen: zustand.regeln.standard_personen || [] });
  if (!vorlage) { zustand.regelVonMail = null; zustand.regelVonVorschlag = null; }
  zustand.bearbeitet = index;
  $('#regel-form-titel').textContent = index >= 0 ? 'Regel ändern' : 'Neue Regel';
  f.name.value = r.name || '';
  f.absender.value = (r.absender || []).join(', ');
  f.betreff.value = (r.betreff || []).join(', ');
  f.empfaenger.value = (r.empfaenger || []).join(', ');
  f.ohne_anhang.checked = !!r.ohne_anhang;
  f.unterordner.value = r.unterordner || '';
  f.thema.textContent = '';
  for (const [schluessel, t] of Object.entries(zustand.themen)) {
    f.thema.add(new Option(t.name || schluessel, schluessel, false, schluessel === r.thema));
  }
  const box = $('#regel-personen');
  box.textContent = '';
  const aktiv = r.personen || zustand.regeln.standard_personen || [];
  for (const [schluessel, p] of Object.entries(zustand.personen)) {
    const l = document.createElement('label');
    const c = document.createElement('input');
    c.type = 'checkbox';
    c.value = schluessel;
    c.checked = aktiv.includes(schluessel);
    l.append(c, ' ' + (p.name || schluessel));
    box.append(l);
  }
  $('#regel-fehler').textContent = '';
  f.hidden = false;
  f.scrollIntoView({ behavior: 'smooth' });
}

const liste = (text) => text.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);

// Prueft eine Regel; liefert Fehlertext oder ''.
function regelPruefen(regel, alle, index) {
  if (!regel.name) return 'Name fehlt.';
  if (alle.some((r, i) => i !== index && r.name === regel.name)) return 'Name ist schon vergeben.';
  if (!regel.absender && !regel.betreff && !regel.empfaenger) return 'Mindestens Absender, Empfänger oder Betreff angeben.';
  if (!(regel.thema in zustand.themen)) return 'Thema unbekannt.';
  if (!regel.personen || !regel.personen.length) return 'Mindestens eine Person wählen.';
  if (!unterordnerGueltig(regel.unterordner)) return 'Unterordner ungültig (keine leeren Teile, kein ..).';
  return '';
}

async function regelnSpeichern(nachricht) {
  zustand.regelSha = await dateiSchreiben(REGEL_DATEI, JSON.stringify(zustand.regeln, null, 2) + '\n',
    zustand.regelSha, nachricht);
  melde('Gespeichert: ' + nachricht, 'gut');
  zeigeRegeln();
}

async function regelAbsenden(ereignis) {
  ereignis.preventDefault();
  const f = $('#regel-form');
  const regel = { name: f.name.value.trim().toLowerCase().replace(/\s+/g, '-') };
  if (liste(f.absender.value).length) regel.absender = liste(f.absender.value);
  if (liste(f.empfaenger.value).length) regel.empfaenger = liste(f.empfaenger.value);
  if (liste(f.betreff.value).length) regel.betreff = liste(f.betreff.value);
  if (f.ohne_anhang.checked) regel.ohne_anhang = true;
  regel.thema = f.thema.value;
  if (f.unterordner.value.trim()) regel.unterordner = f.unterordner.value.trim();
  regel.personen = [...$('#regel-personen').querySelectorAll('input:checked')].map((c) => c.value);
  const fehler = regelPruefen(regel, zustand.regeln.regeln, zustand.bearbeitet);
  if (fehler) { $('#regel-fehler').textContent = fehler; return; }
  if (zustand.bearbeitet >= 0) zustand.regeln.regeln[zustand.bearbeitet] = regel;
  else zustand.regeln.regeln.push(regel);
  try {
    await regelnSpeichern(`regeln: ${regel.name} ${zustand.bearbeitet >= 0 ? 'geändert' : 'neu'} (Web)`);
    const mail = zustand.regelVonMail;
    zustand.regelVonMail = null;
    const vorschlag = zustand.regelVonVorschlag;
    zustand.regelVonVorschlag = null;
    if (vorschlag) await vorschlagErledigt(vorschlag, false);
    if (mail) {
      await eingangAblegen(mail, regel, 'regel/' + regel.name);
      melde(`Regel ${regel.name} gespeichert und Mail abgelegt.`, 'gut');
    }
  } catch (e) { $('#regel-fehler').textContent = e.message; }
}

async function regelLoeschen(index) {
  const r = zustand.regeln.regeln[index];
  if (!confirm(`Regel „${r.name}“ löschen?`)) return;
  zustand.regeln.regeln.splice(index, 1);
  try { await regelnSpeichern(`regeln: ${r.name} gelöscht (Web)`); } catch (e) { melde(e.message, 'fehler'); }
}

async function verwerfenSpeichern() {
  zustand.regeln.verwerfen = $('#verwerfen').value.split('\n').map((s) => s.trim().toLowerCase()).filter(Boolean);
  try { await regelnSpeichern('regeln: Verwerfen-Liste geändert (Web)'); } catch (e) { melde(e.message, 'fehler'); }
}

// Einstellungsdateien (Rohtext mit Pruefung)

let dateiSha = '';

async function zeigeDatei() {
  const pfad = $('#datei-wahl').value;
  $('#datei-fehler').textContent = '';
  try {
    const d = await dateiLesen(pfad);
    $('#datei-inhalt').value = d.text;
    dateiSha = d.sha;
  } catch (e) { melde(e.message, 'fehler'); }
}

async function dateiSpeichern() {
  const pfad = $('#datei-wahl').value;
  const text = $('#datei-inhalt').value;
  try {
    pfad.endsWith('.json') ? JSON.parse(text) : jsyaml.load(text);
  } catch (e) { $('#datei-fehler').textContent = 'Ungültiges Format: ' + e.message; return; }
  try {
    dateiSha = await dateiSchreiben(pfad, text.endsWith('\n') ? text : text + '\n', dateiSha, `config: ${pfad} geändert (Web)`);
    melde(pfad + ' gespeichert.', 'gut');
  } catch (e) { $('#datei-fehler').textContent = e.message; }
}

// Ablaeufe

const STATUS = { queued: 'wartet', in_progress: 'läuft', completed: 'fertig' };
const ERGEBNIS = { success: ['erfolgreich', 'gut'], failure: ['fehlgeschlagen', 'fehler'], cancelled: ['abgebrochen', 'warn'] };

async function zeigeLaeufe() {
  const tbody = $('#laeufe');
  tbody.textContent = '';
  try {
    const d = await gh(`/repos/${zustand.repo}/actions/workflows/${MAIL_WORKFLOW}/runs?per_page=5`);
    for (const lauf of d.workflow_runs) {
      const z = tbody.insertRow();
      const a = document.createElement('a');
      a.href = lauf.html_url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = new Date(lauf.created_at).toLocaleString('de-DE');
      z.insertCell().append(a);
      zelle(z, STATUS[lauf.status] || lauf.status);
      const [text, klasse] = ERGEBNIS[lauf.conclusion] || [lauf.conclusion || '', ''];
      zelle(z, text, klasse);
    }
    if (!d.workflow_runs.length) zelle(tbody.insertRow(), 'Noch keine Läufe.', 'hinweis');
  } catch (e) { melde(e.message, 'fehler'); }
}

async function mailStarten() {
  try {
    await gh(`/repos/${zustand.repo}/actions/workflows/${MAIL_WORKFLOW}/dispatches`, {
      method: 'POST', body: JSON.stringify({ ref: 'main' }),
    });
    melde('Mail-Ablauf gestartet.', 'gut');
    setTimeout(zeigeLaeufe, 3000);
  } catch (e) { melde(e.message, 'fehler'); }
}

// Anmeldung

async function anmelden() {
  zustand.repo = $('#repo').value.trim();
  zustand.token = $('#token').value.trim();
  try {
    await gh(`/repos/${zustand.repo}`);
  } catch (e) {
    $('#anmeldung-fehler').textContent = 'Anmeldung fehlgeschlagen: ' + e.message;
    return;
  }
  merke('sb-repo', zustand.repo);
  merke('sb-token', zustand.token);
  starten();
}

function abmelden() {
  merke('sb-token', '');
  location.reload();
}

function starten() {
  $('#anmeldung').hidden = true;
  $('#reiter').hidden = false;
  $('#abmelden').hidden = false;
  $('#repo-name').textContent = zustand.repo;
  zeigeReiter(lade('sb-reiter') || 'uebersicht');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#reiter button').forEach((b) => b.addEventListener('click', () => zeigeReiter(b.dataset.reiter)));
  $('#anmelden').addEventListener('click', anmelden);
  $('#abmelden').addEventListener('click', abmelden);
  $('#secret-neu').addEventListener('click', () => {
    const name = $('#secret-neu-name').value.trim().toUpperCase();
    if (/^[A-Z_][A-Z0-9_]*$/.test(name)) secretAbfragen(name);
    else melde('Name nur aus A–Z, 0–9 und _.', 'fehler');
  });
  $('#regel-neu').addEventListener('click', () => regelFormular(-1));
  $('#regel-abbrechen').addEventListener('click', () => { $('#regel-form').hidden = true; zustand.regelVonMail = null; });
  $('#regel-form').addEventListener('submit', regelAbsenden);
  $('#verwerfen-speichern').addEventListener('click', verwerfenSpeichern);
  $('#datei-wahl').addEventListener('change', zeigeDatei);
  $('#datei-speichern').addEventListener('click', dateiSpeichern);
  $('#mail-starten').addEventListener('click', mailStarten);

  zustand.repo = lade('sb-repo') || $('#repo').value;
  zustand.token = lade('sb-token');
  $('#repo').value = zustand.repo;
  if (zustand.token) starten();
  else $('#anmeldung').hidden = false;
});
