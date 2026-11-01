// Einstellungsseite des Second Brain. Spricht direkt mit der GitHub-API;
// der Token bleibt im localStorage dieses Browsers.

'use strict';

// Secrets ohne eigenes Konto-Formular (siehe KONTEN). Namen muessen zu den
// Workflows im Daten-Repo passen.
const SECRETS = [
  { name: 'DRIVE_SKRIPT_URL', wofuer: 'Google Drive: wird von „Google Drive verbinden“ gesetzt (optional)' },
  { name: 'DRIVE_SCHLUESSEL', wofuer: 'Google Drive: wird von „Google Drive verbinden“ gesetzt' },
];
const REGEL_DATEI = 'regeln/mail.json';
const VORSCHLAG_DATEI = 'regeln/mail-vorschlaege.json';
const MAIL_WORKFLOW = 'mail.yml';
const ORDNER_DATEI = 'config/ordner.yaml';

const $ = (sel) => document.querySelector(sel);
const zustand = { repo: '', token: '', themen: {}, personen: {}, regeln: null, regelSha: '', bearbeitet: -1, regelVonMail: null, regelVonVorschlag: null, ordner: {}, wissen: [], objekte: {}, steuer: {}, vertraege: [] };

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

function zeigeReiter(name, teil) {
  if (!['start', 'mails', 'einrichtung'].includes(name)) name = 'start';
  document.querySelectorAll('.reiter').forEach((s) => { s.hidden = s.id !== name; });
  document.querySelectorAll('#reiter button').forEach((b) => b.classList.toggle('aktiv', b.dataset.reiter === name));
  merke('sb-reiter', name);
  if (name === 'einrichtung') return zeigeTeil(teil || lade('sb-teil') || 'regeln');
  return ({ start: zeigeStart, mails: zeigeMails })[name]();
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
  const stand = (name) => (gesetzt.has(name) ? 'gesetzt ' + new Date(gesetzt.get(name)).toLocaleDateString('de-DE') : 'fehlt');
  for (const k of KONTEN) {
    const ziel = $('#konto-' + k.id + ' .stand');
    if (!ziel) continue;
    const fehlt = (k.nutzer && !gesetzt.has(k.nutzer)) || !gesetzt.has(k.passwort);
    ziel.textContent = (k.nutzer ? `Adresse ${stand(k.nutzer)}, ` : '') + `${k.feld} ${stand(k.passwort)}`;
    ziel.className = 'stand ' + (fehlt ? 'warn' : 'gut');
  }
  const imKonto = (name) => KONTEN.some((k) => k.nutzer === name || k.passwort === name);
  const liste = [...SECRETS, ...vorhanden.filter((s) => !imKonto(s.name) && !SECRETS.some((b) => b.name === s.name)).map((s) => ({ name: s.name, wofuer: '' }))];
  for (const s of liste) {
    const z = tbody.insertRow();
    zelle(z, s.name);
    zelle(z, s.wofuer, 'hinweis');
    zelle(z, stand(s.name), gesetzt.has(s.name) ? 'gut' : 'warn');
    z.insertCell().append(knopf(gesetzt.has(s.name) ? 'Ändern' : 'Setzen', () => secretBearbeiten(s.name)));
  }
}

// Ein Formular pro Konto mit Nutzername und Passwort, damit der Google
// Passwortmanager beides ausfuellt und nach dem Speichern anbietet, es sich
// zu merken. Alle Passwoerter hier sind eigene App-Passwoerter bzw.
// Schluessel, die es sonst nirgends gibt, also liegt nichts doppelt.
const KONTEN = [
  { id: 'gmx', titel: 'GMX', feld: 'App-Passwort', nutzer: 'MAIL_GMX_USER', passwort: 'MAIL_GMX_PASSWORD', typ: 'email',
    hinweis: 'Nicht dein normales GMX-Passwort: Mit Zwei-Faktor-Anmeldung lässt GMX den Abruf nur mit einem App-Passwort zu. Lege es in den GMX-Sicherheitseinstellungen an. GMX zeigt es nur einmal, lass es Chrome nach dem Speichern merken.' },
  { id: 'gmail', titel: 'Gmail', feld: 'App-Passwort', nutzer: 'MAIL_GMAIL_USER', passwort: 'MAIL_GMAIL_PASSWORD', typ: 'email',
    hinweis: 'Nicht dein Google-Passwort, sondern ein App-Passwort (Google-Konto → Sicherheit → App-Passwörter). Google zeigt es nur einmal, lass es Chrome nach dem Speichern merken.' },
  { id: 'openrouter', titel: 'OpenRouter', feld: 'Schlüssel', fest: 'OpenRouter', passwort: 'OPENROUTER_API_KEY',
    hinweis: 'Für das KI-Einordnen (optional, einschalten in config/einordnen.yaml). OpenRouter zeigt den Schlüssel nur einmal, lass ihn Chrome nach dem Speichern merken.' },
];

function kontenZeigen() {
  const ziel = $('#konten');
  if (ziel.childElementCount) return;
  for (const k of KONTEN) ziel.append(kontoFormular(k));
}

function kontoFormular(k) {
  const form = document.createElement('form');
  form.className = 'karte konto';
  form.id = 'konto-' + k.id;
  const h = document.createElement('h3');
  h.textContent = k.titel;
  const nutzer = document.createElement('input');
  nutzer.name = 'username';
  nutzer.autocomplete = 'username';
  if (k.fest) { nutzer.value = k.fest; nutzer.readOnly = true; } else { nutzer.type = k.typ; nutzer.placeholder = 'Adresse (leer lassen, wenn unverändert)'; }
  const passwort = document.createElement('input');
  passwort.name = 'password';
  passwort.type = 'password';
  passwort.autocomplete = 'new-password';
  const hinweis = document.createElement('p');
  hinweis.className = 'hinweis';
  hinweis.textContent = k.hinweis;
  const stand = document.createElement('p');
  stand.className = 'stand';
  const knopfSpeichern = document.createElement('button');
  knopfSpeichern.type = 'submit';
  knopfSpeichern.textContent = 'Speichern';
  form.append(h, stand, beschriftet(k.fest ? 'Nutzername' : 'Mail-Adresse', nutzer), beschriftet(k.feld, passwort),
    hinweis, knopfSpeichern);
  form.addEventListener('submit', (e) => { e.preventDefault(); kontoSpeichern(k, form); });
  return form;
}

function beschriftet(text, feld) {
  const l = document.createElement('label');
  l.append(text + ' ', feld);
  return l;
}

async function kontoSpeichern(k, form) {
  const nutzer = form.elements.username;
  const passwort = form.elements.password;
  const adresse = k.fest ? '' : nutzer.value.trim();
  const wert = passwort.value;
  if (!wert && !adresse) { melde('Bitte Adresse oder Passwort eingeben.', 'fehler'); return; }
  try {
    melde('Speichere ' + k.titel + ' …');
    if (adresse) await secretSetzen(k.nutzer, adresse);
    if (wert) await secretSetzen(k.passwort, wert);
  } catch (e) { melde(e.message, 'fehler'); return; }
  melde(k.titel + ' gespeichert.', 'gut');
  // Ausblenden nach erfolgreicher Anfrage ist Chromes Zeichen fuer
  // „Anmeldung geklappt“, dann bietet er das Speichern an.
  form.hidden = true;
  const fertig = document.createElement('div');
  fertig.className = 'karte';
  fertig.append(k.titel + ' gespeichert. ', knopf('Erneut ändern', () => { form.remove(); fertig.replaceWith(kontoFormular(k)); zeigeSecrets(); }, 'klein'));
  form.after(fertig);
  setTimeout(() => form.remove(), 5000);
  zeigeSecrets();
}

function secretBearbeiten(name) {
  if (name.startsWith('DRIVE_')) { $('#drive-bereich').scrollIntoView({ behavior: 'smooth' }); return; }
  $('#secret-neu-bereich').open = true;
  $('#secret-neu-name').value = name;
  $('#secret-neu-wert').focus();
}

async function weiteresSecretSpeichern(e) {
  e.preventDefault();
  const name = $('#secret-neu-name').value.trim().toUpperCase();
  const wert = $('#secret-neu-wert').value;
  if (!/^[A-Z_][A-Z0-9_]*$/.test(name)) { melde('Name nur aus A–Z, 0–9 und _.', 'fehler'); return; }
  if (!wert) { melde('Bitte einen Wert eingeben.', 'fehler'); return; }
  try {
    melde('Speichere ' + name + ' …');
    await secretSetzen(name, wert);
  } catch (err) { melde(err.message, 'fehler'); return; }
  melde(name + ' gespeichert.', 'gut');
  $('#secret-neu-bereich').open = false;
  zeigeSecrets();
}

// Google Drive verbinden: Apps-Script im Agentenkonto als Bruecke
// (drive-bruecke/Code.gs). Der Schluessel wird hier erzeugt, in den Code
// eingesetzt und nach erfolgreichem Test als Secret gespeichert.

const BRUECKE_CODE = 'https://raw.githubusercontent.com/HaraldKiessling/second-brain/main/drive-bruecke/Code.gs';
const SCHREIBRECHT = ['EDIT', 'OWNER'];

function driveSchluessel() {
  let s = lade('sb-drive-schluessel');
  if (!s) {
    s = Array.from(crypto.getRandomValues(new Uint8Array(24)), (b) => b.toString(16).padStart(2, '0')).join('');
    merke('sb-drive-schluessel', s);
  }
  return s;
}

async function driveCodeZeigen() {
  const feld = $('#drive-code');
  if (feld.value) return;
  try {
    const r = await fetch(BRUECKE_CODE);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    feld.value = (await r.text()).replace('__SCHLUESSEL__', driveSchluessel());
  } catch (e) { feld.value = 'Code konnte nicht geladen werden: ' + e.message; }
}

async function driveTesten() {
  const url = $('#drive-url').value.trim();
  const erg = $('#drive-ergebnis');
  erg.className = 'hinweis';
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[\w-]+\/exec$/.test(url)) {
    erg.textContent = 'Bitte die Web-App-URL einfügen (beginnt mit https://script.google.com/macros/s/ und endet auf /exec).';
    return;
  }
  erg.textContent = 'Teste …';
  let a;
  try {
    await stammdatenLaden();
    // Laufendes und naechstes Jahr, aeltere Jahresordner und 0000-dauerhaft
    const ids = [...new Set([...Object.values(zustand.themen).flatMap((t) => Object.values(t.drive || {})),
      ...Object.values(zustand.jahre || {}), ...(zustand.dauerhaft ? [zustand.dauerhaft.id] : [])].filter(Boolean))];
    // text/plain vermeidet die CORS-Vorabfrage, die Apps-Script nicht beantwortet.
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify({ aktion: 'pruefen', schluessel: driveSchluessel(), ordner_ids: ids }) });
    a = await r.json();
  } catch (e) {
    erg.textContent = `Skript nicht erreichbar. Ist der Zugriff auf „Jeder“ gestellt? (${e.message})`;
    erg.className = 'fehler';
    return;
  }
  if (!a.ok) {
    erg.textContent = 'Das Skript meldet: ' + a.fehler + (a.fehler === 'Schluessel falsch' ? '. Bitte den Code oben neu kopieren und neu bereitstellen.' : '');
    erg.className = 'fehler';
    return;
  }
  const gut = a.ordner.filter((o) => SCHREIBRECHT.includes(o.recht));
  const schlecht = a.ordner.filter((o) => !gut.includes(o));
  erg.textContent = `Verbunden als ${a.konto}. ${gut.length} von ${a.ordner.length} Ordnern beschreibbar.`;
  if (schlecht.length) {
    const ul = document.createElement('ul');
    for (const o of schlecht) {
      const li = document.createElement('li');
      li.textContent = `${o.name || o.id}: ${o.fehler || 'nur Leserecht (' + o.recht + ')'}`;
      ul.append(li);
    }
    erg.append(ul);
  }
  if (!gut.length) { erg.className = 'fehler'; return; }
  try {
    await secretSetzen('DRIVE_SKRIPT_URL', url);
    await secretSetzen('DRIVE_SCHLUESSEL', driveSchluessel());
    erg.className = 'gut';
    melde('Google Drive verbunden. Ab dem nächsten Abruf landen Anhänge in den Ordnern.', 'gut');
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

// --- Pfade wie in Drive ------------------------------------------------------
// Harald soll die Ordner so sehen, wie sie in seinem Drive heissen:
// "2026 › 08Versicherungen › 07HUK_Kfz_624_220429-P". Das laufende Jahr heisst
// in Drive "0-2026" (damit es oben steht); angezeigt wird nur "2026".

const ZEICHEN = ' › ';

function jahrZahl(schluessel) {
  const m = /^(?:0-)?(\d{4})$/.exec(String(schluessel || ''));
  return m ? Number(m[1]) : null;
}

// Jahresordner fuer eine Jahreszahl (oder ein Datum "2026-10-28")
function jahrOrdner(jahr) {
  const j = Number(String(jahr).slice(0, 4));
  return j === new Date().getFullYear() ? `0-${j}` : String(j);
}

// ID aus { "0-2026": id, "2025": id } fuer ein Jahr; Schluessel mit oder ohne 0-
function idFuerJahr(ids, jahr) {
  for (const [k, v] of Object.entries(ids || {})) if (jahrZahl(k) === Number(jahr)) return v;
  return '';
}

function themaOrdner(thema) {
  const t = zustand.themen[thema] || {};
  return t.ablage || t.name || thema || '';
}

// "2026 › 01Gebäude › atu"; ohne Jahr nur Themenordner und Unterordner
function pfadText(jahr, thema, uo) {
  return [jahr ? String(jahrZahl(jahr) || jahr) : '', themaOrdner(thema), ...String(uo || '').split('/')]
    .map((t) => t.trim()).filter(Boolean).join(ZEICHEN);
}

// Gespeicherte Ablage "0-2026/01Gebäude/atu" -> "2026 › 01Gebäude › atu"
function ablageText(ablage) {
  const teile = String(ablage || '').split('/').filter(Boolean);
  if (teile.length && jahrZahl(teile[0])) teile[0] = String(jahrZahl(teile[0]));
  return teile.join(ZEICHEN);
}

function jahrAusAblage(ablage) {
  return jahrZahl(String(ablage || '').split('/')[0]);
}

// Link auf den Drive-Ordner: der genaue Unterordner, wenn seine ID bekannt ist
// (laufendes Jahr, config/ordner.yaml: ids), sonst Themen- oder Jahresordner.
function ordnerLink(jahr, thema, uo) {
  const ids = (zustand.themen[thema] || {}).drive || {};
  const teile = String(uo || '').split('/').map((t) => t.trim()).filter(Boolean);
  if (`0-${jahr}` in ids) {
    for (let i = teile.length; i > 0; i--) {
      const id = (zustand.ordnerIds || {})[`${thema}/${teile.slice(0, i).join('/')}`];
      if (id) return `https://drive.google.com/drive/folders/${id}`;
    }
  }
  const id = idFuerJahr(ids, jahr) || idFuerJahr(zustand.jahre, jahr);
  return id ? `https://drive.google.com/drive/folders/${id}` : '';
}

function link(text, href, klasse = '') {
  const a = document.createElement('a');
  a.href = href; a.target = '_blank'; a.rel = 'noopener';
  a.textContent = text;
  if (klasse) a.className = klasse;
  return a;
}

function el(tag, klasse, text) {
  const e = document.createElement(tag);
  if (klasse) e.className = klasse;
  if (text !== undefined) e.textContent = text;
  return e;
}

// Soll-Ort in Drive wie drive.ziel(): "<ordner-id>:<pfad>".
function driveZiel(meta) {
  const thema = (meta.themen || [])[0];
  const t = zustand.themen[thema] || {};
  const teile = String(meta.ablage || '').split('/');
  const jahr = jahrZahl(teile[0]);
  if (teile.length >= 2 && jahr && teile[1] === t.ablage) {
    const id = idFuerJahr(t.drive, jahr);
    if (id) return `${id}:${teile.slice(2).join('/')}`;
    const jid = idFuerJahr(zustand.jahre, jahr);
    if (jid) return `${jid}:${teile.slice(1).join('/')}`;
  }
  return `:${SAMMELORDNER}/${meta.id}`;
}

// Was liegt wo: Zeilen [symbol, text, ziel, link, klasse] fuer eine Notiz oder
// eine geplante Ablage (plan: { pfad, link, mail_drive, dauerhaft }).
function wasWo(meta, plan) {
  const zeilen = [];
  const anhaenge = (meta && meta.anhaenge) || [];
  const ids = (meta && meta.dateien) || {};
  const liegt = !plan && meta && meta.drive === driveZiel(meta);
  for (const a of anhaenge) {
    const id = ids[String(a).split('/').pop()];
    const dort = plan ? 'kommt nach' : liegt ? 'liegt in' : meta.drive ? 'wird verschoben nach' : 'kommt nach';
    zeilen.push(['📎', `Anhang ${a}`, dort, liegt && id ? `https://drive.google.com/file/d/${id}/view` : '', liegt ? 'gut' : '']);
  }
  const pdf = plan ? plan.mail_drive : meta && meta.mail_drive;
  if (pdf) {
    const da = !plan && meta.mail_pdf && meta.mail_pdf === driveZiel(meta);
    zeilen.push(['✉️', 'Mail als PDF', da ? 'liegt in' : 'kommt nach',
      da && meta.mail_pdf_id ? `https://drive.google.com/file/d/${meta.mail_pdf_id}/view` : '', da ? 'gut' : '']);
  } else if (!plan && meta && meta.mail_pdf) {
    zeilen.push(['✉️', 'Mail als PDF', 'kommt in den Papierkorb', '', 'warn']);
  }
  if (!anhaenge.length && !pdf) zeilen.push(['📝', 'Keine Datei angehängt:', 'nur der Text kommt ins Second Brain. Soll die Mail selbst nach Drive, wähle unter „Mehr“ „Mail als PDF“.', '', 'hinweis']);
  else zeilen.push(['📝', 'Text und Zusammenfassung', 'im Second Brain (Notiz)', '', 'hinweis']);
  const dauerhaft = plan ? plan.dauerhaft : meta && meta.dauerhaft;
  if (dauerhaft) {
    const da = !plan && meta.drive_dauerhaft;
    const name = (zustand.dauerhaft && zustand.dauerhaft.name) || '0000-dauerhaft';
    zeilen.push(['🗄️', 'Kopie', `${da ? 'liegt in' : 'kommt nach'} ${name}${ZEICHEN}${dauerhaft === true ? '' : dauerhaft}`,
      zustand.dauerhaftOrdner && zustand.dauerhaftOrdner[dauerhaft] ? `https://drive.google.com/drive/folders/${zustand.dauerhaftOrdner[dauerhaft]}` : '', da ? 'gut' : '']);
  }
  return zeilen;
}

function wasWoListe(zeilen, pfad) {
  const ul = el('ul', 'waswo');
  for (const [symbol, was, wo, href, klasse] of zeilen) {
    const li = el('li', klasse);
    li.append(el('span', 'symbol', symbol), href ? link(was, href) : el('span', '', was), el('span', 'hinweis', ` ${wo}`));
    if (/kommt nach$|liegt in$|verschoben nach$/.test(wo) && pfad) li.lastChild.textContent += ` ${pfad}`;
    ul.append(li);
  }
  return ul;
}

// --- Ordnerauswahl ----------------------------------------------------------
// Alle bekannten Ordner: Themenordner, config/ordner.yaml, Ablagewissen und
// Regeln. Fuer eine Mail kommen die wahrscheinlichsten nach oben.

const ordnerSchluessel = (thema, uo) => `${thema}\t${uo || ''}`;

function bekannteOrdner() {
  const alle = new Map();
  const dazu = (thema, uo, quelle) => {
    if (!(thema in zustand.themen)) return;
    const k = ordnerSchluessel(thema, (uo || '').replace(/^\/+|\/+$/g, ''));
    if (!alle.has(k)) alle.set(k, { thema, unterordner: (uo || '').replace(/^\/+|\/+$/g, ''), quelle });
  };
  for (const t of Object.keys(zustand.themen)) dazu(t, '', 'Themenordner');
  // Nur die Ordnerliste (echter Drive-Baum) zaehlt als bestehend. Ziele aus
  // Ablagewissen, Vertraegen und Regeln erscheinen nur, wenn sie passen, und dann als neu.
  for (const [t, liste] of Object.entries(zustand.ordner || {})) for (const uo of liste || []) dazu(t, String(uo), 'Ordnerliste');
  return alle;
}

// Ziffernfolgen ab 6 Stellen ohne Trennzeichen (624/220429-P -> 624220429), wie nummern() in einordnen.py
function nummern(text) {
  return new Set((String(text || '').match(/\d(?:[\s/._-]*\d)+/g) || []).map((z) => z.replace(/\D/g, '')).filter((z) => z.length >= 6));
}
const schnitt = (a, b) => [...a].some((x) => b.has(x));

// Woerter fuer den Vergleich: klein, ohne Umlaute, ohne Ziffern.
function woerter(text) {
  return String(text || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .split(/[^a-z]+/).filter((w) => w.length >= 3);
}
const wortPasst = (a, b) => a === b || (a.length >= 5 && b.length >= 5 && (a.startsWith(b) || b.startsWith(a)));
const OHNE_GEWICHT = new Set(['und', 'der', 'die', 'das', 'mit', 'fuer', 'von', 'ihre', 'ihr', 'sie', 'wir', 'zum', 'zur', 'den', 'dem', 'des',
  'privat', 'harald', 'ausgaben', 'sonstiges', 'weitere', 'kosten', 'neu', 'http', 'https', 'www']);

// kontext: { absender, betreff, text, anhaenge, vorschlag }
// Ergebnis: [{ thema, unterordner, punkte, gruende }], wahrscheinlichste zuerst.
function ordnerRangliste(kontext) {
  const alle = bekannteOrdner();
  const punkte = new Map();
  const gib = (thema, uo, n, grund) => {
    const k = ordnerSchluessel(thema, uo);
    if (!alle.has(k)) alle.set(k, { thema, unterordner: uo || '', quelle: 'Vorschlag' });
    const p = punkte.get(k) || { punkte: 0, gruende: [] };
    p.punkte += n;
    if (grund && !p.gruende.includes(grund)) p.gruende.push(grund);
    punkte.set(k, p);
  };
  if (kontext.aktuell && kontext.aktuell.thema in zustand.themen) {
    gib(kontext.aktuell.thema, (kontext.aktuell.unterordner || '').replace(/^\/+|\/+$/g, ''), 1, 'liegt jetzt hier');
  }
  const v = kontext.vorschlag;
  for (const a of v && v.thema ? [v, ...(v.alternativen || [])] : []) {
    if (a.thema in zustand.themen) gib(a.thema, (a.unterordner || '').replace(/^\/+|\/+$/g, ''), 2 + 3 * (a.konfidenz || 0), `Vorschlag ${Math.round((a.konfidenz || 0) * 100)} %`);
  }
  const roh = [kontext.absender, kontext.betreff, ...(kontext.anhaenge || [])].join(' ').toLowerCase();
  for (const w of zustand.wissen || []) {
    const gefunden = (w.muster || []).map(String).filter((m) => roh.includes(m.toLowerCase()));
    if (gefunden.length) gib(w.thema, String(w.unterordner || ''), 1.5 * gefunden.length, gefunden.join(', '));
  }
  // Vertragsnummern: Vertragsliste und Nummern in Ordnernamen
  const imBetreff = nummern([kontext.betreff, ...(kontext.anhaenge || [])].join(' '));
  const ueberall = new Set([...imBetreff, ...nummern(kontext.text)]);
  for (const v of zustand.vertraege || []) {
    if (schnitt(nummern(v.nummer), ueberall)) gib(v.thema, String(v.unterordner || ''), 8, `Vertrag ${v.nummer}`);
  }
  for (const o of [...alle.values()]) {
    const eigene = nummern(o.unterordner);
    if (!eigene.size) continue;
    if (schnitt(eigene, ueberall)) gib(o.thema, o.unterordner, 6, 'Vertragsnummer passt');
    else if (imBetreff.size) gib(o.thema, o.unterordner, -6, 'andere Vertragsnummer');
  }
  // Woerter aus Betreff (doppelt), Anhaengen und Mailtext gegen Ordnernamen
  const kopf = new Set(woerter([kontext.betreff, ...(kontext.anhaenge || [])].join(' ')));
  // Mailtext bis zur Grussformel, der Fuss (Telefon, Impressum) verfaelscht sonst
  const text = String(kontext.text || '').split(/\n\s*(mit freundlichen gr|viele gr|beste gr|freundliche gr|kind regards|best regards)/i)[0];
  const rumpf = new Set(woerter(text.slice(0, 3000)));
  for (const o of alle.values()) {
    const t = zustand.themen[o.thema] || {};
    const namen = new Set([...woerter(t.name), ...woerter(t.ablage), ...woerter(o.unterordner), ...(t.stichwoerter || []).flatMap(woerter)]);
    for (const n of namen) {
      if (OHNE_GEWICHT.has(n)) continue;
      // Ein Treffer im Unterordner zaehlt fuer diesen Ordner, nicht fuer das ganze Thema
      const tief = woerter(o.unterordner).includes(n) ? 1 : 0.6;
      if ([...kopf].some((w) => wortPasst(w, n))) gib(o.thema, o.unterordner, 1.2 * tief, `„${n}“ im Betreff`);
      else if ([...rumpf].some((w) => wortPasst(w, n))) gib(o.thema, o.unterordner, 0.5 * tief, `„${n}“ in der Mail`);
    }
  }
  return [...alle.entries()].map(([k, o]) => ({ ...o, ...(punkte.get(k) || { punkte: 0, gruende: [] }) }))
    .sort((a, b) => b.punkte - a.punkte);
}

// Ordner so, wie er in Drive heisst: "08Versicherungen › 07HUK_Kfz_624_220429-P"
function ordnerName(o) {
  return pfadText('', o.thema, o.unterordner);
}

// Suchtext eines Ordners: Drive-Name plus Anzeigename des Themas
function ordnerSuchtext(o) {
  const t = zustand.themen[o.thema] || {};
  return `${ordnerName(o)} ${t.name || ''} ${o.thema}`;
}

function ordnerBekannt(thema, uo) {
  return bekannteOrdner().has(ordnerSchluessel(thema, String(uo || '').replace(/^\/+|\/+$/g, '')));
}

// Haekchen-Gruppe: eintraege { schluessel: { name } }
function haekchen(legende, eintraege, aktiv = []) {
  const f = document.createElement('fieldset');
  const l = document.createElement('legend');
  l.textContent = legende;
  f.append(l);
  for (const [k, e] of Object.entries(eintraege)) {
    const lab = document.createElement('label');
    const c = document.createElement('input');
    c.type = 'checkbox'; c.value = k; c.checked = aktiv.includes(k);
    lab.append(c, ' ' + ((e && e.name) || k));
    f.append(lab);
  }
  f.werte = () => [...f.querySelectorAll('input:checked')].map((c) => c.value);
  f.setzen = (liste = []) => f.querySelectorAll('input').forEach((c) => { c.checked = liste.includes(c.value); });
  return f;
}

// Weitere Themen, Objekte, Steuerbezuege (aufklappbar). Liefert Element mit werte()/setzen().
function bezuegeFelder(vorgabe = {}) {
  const d = document.createElement('details');
  d.className = 'bezuege';
  const s = document.createElement('summary');
  const themen = haekchen('Weitere Themen (auch dort auffindbar)', zustand.themen, vorgabe.weitere_themen || []);
  const objekte = haekchen('Objekt', zustand.objekte, vorgabe.objekte || []);
  const steuer = haekchen('Steuerbezug', zustand.steuer, vorgabe.steuer || []);
  const teile = [themen, ...(Object.keys(zustand.objekte).length ? [objekte] : []), ...(Object.keys(zustand.steuer).length ? [steuer] : [])];
  const zusammenfassen = () => {
    const namen = (liste, quelle) => liste.map((k) => ((quelle[k] || {}).name || k).split(' (')[0]);
    const alle = [...namen(themen.werte(), zustand.themen), ...namen(objekte.werte(), zustand.objekte), ...namen(steuer.werte(), zustand.steuer)];
    s.textContent = 'Weitere Themen, Objekt, Steuerbezug' + (alle.length ? ': ' + alle.join(', ') : '');
  };
  d.append(s, ...teile);
  d.addEventListener('change', zusammenfassen);
  d.werte = () => ({ weitere_themen: themen.werte(), objekte: objekte.werte(), steuer: steuer.werte() });
  d.setzen = (v = {}) => {
    themen.setzen(v.weitere_themen || []); objekte.setzen(v.objekte || []); steuer.setzen(v.steuer || []);
    zusammenfassen();
    if ((v.weitere_themen || []).length || (v.objekte || []).length || (v.steuer || []).length) d.open = true;
  };
  d.setzen(vorgabe);
  return d;
}

function auswahlFelder(vorgabe, kontext = {}) {
  const box = document.createElement('div');
  box.className = 'auswahl';
  const rang = ordnerRangliste({ ...kontext, aktuell: !kontext.vorschlag && vorgabe.thema ? vorgabe : null });
  const oben = rang.filter((o) => o.punkte > 0).slice(0, 8);
  const reihenfolge = Object.keys(zustand.themen);
  const sortiert = [...rang].sort((a, b) =>
    reihenfolge.indexOf(a.thema) - reihenfolge.indexOf(b.thema) || a.unterordner.localeCompare(b.unterordner, 'de'));
  // Suchfeld mit Liste: leer = wahrscheinlichste oben, dann alle; Tippen filtert;
  // ein Pfad, den es nicht gibt, wird als neuer Ordner angeboten.
  const suche = document.createElement('input');
  suche.className = 'ordnersuche';
  suche.placeholder = 'Ordner suchen, z. B. HUK, oder neuen Pfad: Versicherungen / HUK Kfz';
  suche.autocomplete = 'off';
  const liste = document.createElement('div');
  liste.className = 'ordnerliste';
  liste.setAttribute('role', 'listbox');
  const lo = document.createElement('label'); lo.append('Ordner in Drive (wahrscheinlichste oben, tippen zum Suchen)', suche);
  const norm = (t) => String(t || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
  // "Thema / a / b" -> { thema, unterordner }; erstes Glied = Thema (Name oder Schluessel)
  const zerlegen = (text) => {
    const teile = String(text).split(/\/|›/).map((t) => t.trim()).filter(Boolean);
    if (!teile.length) return null;
    const passt = Object.entries(zustand.themen).filter(([k, t]) => [k, t.name, t.ablage].some((x) => norm(x) === norm(teile[0])));
    const ohneNr = (x) => norm(x).replace(/^[\d_\s]+/, '');
    const anfang = passt.length ? passt : Object.entries(zustand.themen).filter(([k, t]) => [t.name || k, t.ablage].some((x) => ohneNr(x).startsWith(ohneNr(teile[0]))));
    if (anfang.length === 1) return { thema: anfang[0][0], unterordner: teile.slice(1).join('/') };
    if (thema.value) return { thema: thema.value, unterordner: teile.join('/') };
    return null;
  };
  let gewaehlt = '';
  const eintrag = (o, text, klasse = '') => {
    const d = document.createElement('div');
    d.className = 'eintrag ' + klasse + (ordnerSchluessel(o.thema, o.unterordner) === gewaehlt ? ' gewaehlt' : '');
    d.setAttribute('role', 'option');
    d.textContent = text;
    d.addEventListener('mousedown', (ev) => ev.preventDefault());
    d.addEventListener('click', () => waehlen(o));
    return d;
  };
  const kopf = (text) => { const h = document.createElement('div'); h.className = 'kopf'; h.textContent = text; return h; };
  let erster = null;
  const zeigen = () => {
    liste.textContent = '';
    erster = null;
    const q = norm(suche.value).split(/[\s/›]+/).filter(Boolean);
    const gewaehltName = gewaehlt ? norm(ordnerName({ thema: gewaehlt.split('\t')[0], unterordner: gewaehlt.split('\t')[1] })) : '';
    if (!q.length || norm(suche.value) === gewaehltName) {
      if (oben.length) liste.append(kopf('Wahrscheinlich'));
      for (const o of oben) liste.append(eintrag(o, `${ordnerName(o)}${ordnerBekannt(o.thema, o.unterordner) ? '' : ' (neu)'}  ·  ${o.gruende.slice(0, 2).join(', ')}`));
      liste.append(kopf('Alle Ordner in Drive'));
      for (const o of sortiert.filter((x) => ordnerBekannt(x.thema, x.unterordner))) {
        const tiefe = o.unterordner ? o.unterordner.split('/').length : 0;
        liste.append(eintrag(o, '\u00a0\u00a0\u00a0'.repeat(tiefe) + (tiefe ? o.unterordner.split('/').pop() : ordnerName(o))));
      }
      erster = oben[0] || null;
      return;
    }
    const treffer = rang.filter((o) => { const n = norm(ordnerSuchtext(o)); return q.every((w) => n.includes(w)); });
    const ziel = zerlegen(suche.value);
    const neuerPfad = ziel && ziel.unterordner && unterordnerGueltig(ziel.unterordner) && !ordnerBekannt(ziel.thema, ziel.unterordner);
    for (const o of treffer.slice(0, 30)) liste.append(eintrag(o, ordnerName(o) + (ordnerBekannt(o.thema, o.unterordner) ? '' : ' (neu)') + (o.punkte > 0 ? `  ·  ${o.gruende.slice(0, 2).join(', ')}` : '')));
    if (neuerPfad) liste.append(eintrag(ziel, `➕ Neuer Ordner: ${ordnerName(ziel)}`, 'neu'));
    if (!treffer.length && !neuerPfad) liste.append(kopf('Kein Ordner gefunden. Tippe „Thema / Unterordner“ für einen neuen.'));
    erster = treffer[0] || (neuerPfad ? ziel : null);
  };
  suche.addEventListener('input', zeigen);
  suche.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); if (erster) waehlen(erster); } });

  const reihe = document.createElement('div');
  reihe.className = 'reihe';
  const thema = document.createElement('select');
  thema.add(new Option('– Thema wählen –', ''));
  for (const [k, t] of Object.entries(zustand.themen)) thema.add(new Option(t.name || k, k, false, k === vorgabe.thema));
  const uo = document.createElement('input');
  uo.value = vorgabe.unterordner || '';
  uo.placeholder = 'leer = Themenordner, Ebenen mit /';
  const l1 = document.createElement('label'); l1.append('Thema', thema);
  const l2 = document.createElement('label'); l2.append('Unterordner (auch neu)', uo);
  reihe.append(l1, l2);
  const neu = document.createElement('div');
  neu.className = 'hinweis neu';
  const abgleichen = () => {
    const u = uo.value.trim().replace(/^\/+|\/+$/g, '');
    gewaehlt = thema.value ? ordnerSchluessel(thema.value, u) : '';
    if (document.activeElement !== suche) suche.value = thema.value ? ordnerName({ thema: thema.value, unterordner: u }) : '';
    neu.textContent = thema.value && u && !ordnerBekannt(thema.value, u)
      ? 'Neuer Ordner: wird beim Ablegen in Drive angelegt.' : '';
    zeigen();
    if (box.beiAenderung && gestartet) box.beiAenderung();
  };
  let gestartet = false;
  function waehlen(o) {
    thema.value = o.thema; uo.value = o.unterordner || '';
    suche.value = ordnerName(o);
    abgleichen();
  }
  thema.addEventListener('change', abgleichen);
  uo.addEventListener('input', abgleichen);

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
  const bezuege = bezuegeFelder(vorgabe);
  // Thema und Unterordner von Hand: selten noetig, deshalb eingeklappt
  const hand = document.createElement('details');
  hand.className = 'von-hand';
  const hs = document.createElement('summary');
  hs.textContent = 'Thema und Unterordner von Hand eingeben';
  hand.append(hs, reihe);
  const ordnerTeil = document.createElement('div');
  ordnerTeil.className = 'ordnerwahl';
  ordnerTeil.append(lo, liste, neu, hand);
  box.append(ordnerTeil, personen, bezuege);
  box.teile = { ordner: ordnerTeil, personen, bezuege, suche };
  box.vorschlagOben = () => oben[0] || {};
  abgleichen();
  gestartet = true;
  personen.addEventListener('change', () => box.beiAenderung && box.beiAenderung());
  bezuege.addEventListener('change', () => box.beiAenderung && box.beiAenderung());
  box.wert = () => ({
    thema: thema.value,
    unterordner: uo.value.trim(),
    personen: [...personen.querySelectorAll('input:checked')].map((c) => c.value),
    ...bezuege.werte(),
  });
  box.setzen = (v) => {
    thema.value = v.thema || '';
    uo.value = v.unterordner || '';
    if (v.personen && v.personen.length) {
      personen.querySelectorAll('input').forEach((c) => { c.checked = v.personen.includes(c.value); });
    }
    bezuege.setzen(v);
    abgleichen();
  };
  return box;
}

const notizBezuege = (meta) => ({ weitere_themen: (meta.themen || []).slice(1), objekte: meta.objekte || [], steuer: meta.steuer || [] });

// Neue Vorschlaege anfordern: Feld vorschlag_anfordern in der Notiz, der Abruf
// fragt die KI (mit Haralds Hinweis) und schreibt den Vorschlag zurueck.
async function vorschlaegeAnfordern(pfad, hinweis) {
  await commitMehrere(async () => {
    const { text } = await dateiLesen(pfad);
    const n = notizLesen(text);
    n.meta.vorschlag_anfordern = hinweis.trim() || true;
    delete n.meta.vorschlag_fehler;
    return [{ pfad, text: notizSchreiben(n.meta, n.text) }];
  }, `vorschlag: ${pfad.split('/').pop().replace(/\.md$/, '')} neue Vorschläge angefordert (Web)`);
  melde('Neue Vorschläge angefordert.', 'gut');
  await abrufStarten();
}

// Zeile "Neue Vorschläge" mit Hinweisfeld; Zustand aus der Notiz.
function anfordernZeile(e) {
  const box = document.createElement('div');
  box.className = 'anfordern';
  const status = document.createElement('div');
  status.className = 'hinweis';
  if (e.meta.vorschlag_anfordern) {
    status.textContent = 'Neue Vorschläge sind angefordert und kommen mit dem laufenden Abruf (etwa 1–2 Minuten, dann neu laden).';
  } else if (e.meta.vorschlag_fehler) {
    status.textContent = 'Letzte Anforderung ohne Ergebnis: ' + e.meta.vorschlag_fehler;
  }
  const reihe = document.createElement('div');
  reihe.className = 'reihe';
  const hinweis = document.createElement('input');
  hinweis.placeholder = 'Hinweis für die KI (optional), z. B. neues Auto, Kfz-Versicherung';
  const l = document.createElement('label'); l.append('Passt nichts? Neue Vorschläge der KI', hinweis);
  const k = knopf('Neue Vorschläge', async () => {
    k.disabled = true;
    try {
      await vorschlaegeAnfordern(e.pfad, hinweis.value);
      status.textContent = 'Angefordert. Die neuen Vorschläge erscheinen nach dem Abruf (etwa 1–2 Minuten, dann neu laden).';
    } catch (err) { status.textContent = err.message; k.disabled = false; }
  }, 'leise');
  reihe.append(l);
  box.append(reihe, k, status);
  return box;
}

// Kontext fuer die Rangliste aus einer Notiz oder einem Eingang
function mailKontext(e, vorschlag) {
  return { absender: absenderAdresse(e), betreff: titelVon(e.text), text: e.text,
    anhaenge: e.meta.anhaenge || [], vorschlag };
}

function pdfHaken(an, text = 'Mail zusätzlich als PDF in den Drive-Ordner legen (z. B. Buchungsbestätigung)') {
  const l = document.createElement('label');
  l.className = 'haken';
  const c = document.createElement('input');
  c.type = 'checkbox';
  c.checked = an;
  l.append(c, text);
  l.an = () => c.checked;
  return l;
}

function auswahlPruefen(w) {
  if (!(w.thema in zustand.themen)) return 'Bitte ein Thema wählen.';
  if (!w.personen.length) return 'Mindestens eine Person wählen.';
  if (!unterordnerGueltig(w.unterordner)) return 'Unterordner ungültig (keine leeren Teile, kein ..).';
  return '';
}

// Eingang -> Notiz unter notizen/<jahr>/<thema>/, mit Protokollzeile, ein Commit.
// weitere: zusaetzliche Aenderungen fuer denselben Commit (z. B. Indexzeile entfernen).
// w.jahr: Jahresordner (Zugehoerigkeit, bei Zahlungen das Jahr des Geldflusses);
// w.dauerhaft: Unterordner in 0000-dauerhaft fuer eine Kopie oder ''.
async function eingangAblegen(e, w, durch, wie = 'aus Eingang abgelegt', weitere = async () => [], opts = {}) {
  const meta = { ...e.meta };
  const datum = String(meta.erstellt);
  delete meta.offen_grund;
  delete meta.vorschlag;
  delete meta.konfidenz;
  const thema = zustand.themen[w.thema] || {};
  meta.themen = [w.thema, ...(w.weitere_themen || []).filter((t) => t !== w.thema && t in zustand.themen)];
  for (const feld of ['objekte', 'steuer']) {
    if ((w[feld] || []).length) meta[feld] = w[feld];
    else delete meta[feld];
  }
  delete meta.vorschlag_fehler;
  delete meta.vorschlag_anfordern;
  meta.personen = w.personen;
  const jahr = Number(w.jahr || jahrAusAblage(meta.ablage) || datum.slice(0, 4));
  if (jahr !== Number(datum.slice(0, 4))) {
    meta.jahr = jahr;
    meta.jahr_grund = opts.jahrGrund || (meta.jahr_grund && Number(e.meta.jahr) === jahr ? meta.jahr_grund : 'von Harald gewählt');
  } else {
    delete meta.jahr;
    delete meta.jahr_grund;
  }
  meta.ablage = [jahrOrdner(jahr), thema.ablage, unterordnerEinsetzen(w.unterordner, `${jahr}${datum.slice(4)}`)].filter(Boolean).join('/');
  meta.eingeordnet_durch = durch;
  if (w.mail_drive) meta.mail_drive = true;
  else if ('mail_drive' in w) delete meta.mail_drive;  // liegt schon ein PDF, raeumt der Abruf es weg
  if ('dauerhaft' in w) {
    if (w.dauerhaft) { meta.dauerhaft = w.dauerhaft; delete meta.dauerhaft_nein; } else {
      delete meta.dauerhaft;  // liegt schon eine Kopie, raeumt der Abruf sie weg
      if (meta.dauerhaft_vorschlag) meta.dauerhaft_nein = true;
    }
  }
  if (!meta.absender && absenderAdresse(e)) meta.absender = absenderAdresse(e);
  const ziel = `notizen/${datum.slice(0, 4)}/${w.thema}/${meta.id}.md`;
  const heute = new Date().toISOString().slice(0, 10);
  const protokoll = `protokoll/${heute.slice(0, 7)}.md`;
  await commitMehrere(async () => [
    { pfad: ziel, text: notizSchreiben(meta, e.text) },
    ...(e.pfad && ziel !== e.pfad ? [{ pfad: e.pfad, loeschen: true }] : []),
    { pfad: protokoll, text: protokollZeile(await dateiOderLeer(protokoll), heute, durch, `Notiz \`${meta.id}\` ${wie}`) },
    ...await ordnerMerken(w.thema, w.unterordner, w.dauerhaft),
    ...await weitere(),
  ], `${!e.pfad ? 'index' : e.pfad.startsWith('eingang/') ? 'eingang' : 'korrektur'}: ${meta.id} -> ${w.thema} (Web)`);
  melde(`Abgelegt in ${ablageText(meta.ablage)}.`, 'gut');
  e.meta = meta;
  e.pfad = ziel;
  return ziel;
}

// Ein neuer Unterordner kommt beim Ablegen in config/ordner.yaml, damit er
// beim naechsten Mal in der Auswahl steht (auch in 0000-dauerhaft).
async function ordnerMerken(thema, uo, dauerhaft) {
  uo = String(uo || '').trim().replace(/^\/+|\/+$/g, '');
  const d = typeof dauerhaft === 'string' ? dauerhaft.trim() : '';
  const alt = await dateiOderLeer(ORDNER_DATEI);
  const daten = jsyaml.load(alt) || {};
  const ordner = daten.ordner || {};
  const neuUo = uo && !(ordner[thema] || []).map(String).includes(uo);
  const neuD = d && !(d in (daten.dauerhaft || {}));
  if (!neuUo && !neuD) return [];
  if (neuUo) ordner[thema] = [...new Set([...(ordner[thema] || []).map(String), uo])].sort((a, b) => a.localeCompare(b, 'de'));
  if (neuD) daten.dauerhaft = { ...(daten.dauerhaft || {}), [d]: '' };
  daten.ordner = ordner;
  zustand.ordner = ordner;
  return [{ pfad: ORDNER_DATEI, text: ordnerDateiText(alt, daten) }];
}

// config/ordner.yaml schreiben, Kopfkommentar behalten
function ordnerDateiText(alt, daten) {
  const i = alt.indexOf('\nordner:');
  const kopf = i >= 0 ? alt.slice(0, i + 1) : '# Bekannte Unterordner der Drive-Ablage je Thema (Pfad unterhalb des Themenordners,\n'
    + '# Ebenen mit /). Die Web-App bietet sie in der Ordnerauswahl an und ergaenzt neue beim Ablegen.\n';
  const { ordner, ...rest } = daten;
  return kopf + jsyaml.dump({ ordner, ...rest }, { lineWidth: -1 });
}



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

// Mails: alle Mails eines Monats mit Ablageort; Ablage aendern, Indexmail zur
// Notiz machen, Mail als PDF nach Drive. Was dafuer das Postfach braucht
// (voller Text, Anhaenge, PDF), erledigt der naechste Abruf (second-brain nachholen).

const SAMMELORDNER = 'Second Brain Eingang';

function slug(text, laenge) {
  const s = text.toLowerCase().normalize('NFKD').replace(/ß/g, 'ss').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return s.slice(0, laenge).replace(/-+$/, '') || 'ohne-titel';
}

// Wie _absender_kurz in mail.py, damit die ID dem Abruf gleicht.
function absenderKurz(absender) {
  const m = /^\s*"?([^"<]*?)"?\s*<([^>]+)>/.exec(absender);
  const name = m ? m[1].trim() : '';
  const adresse = m ? m[2] : absender.trim();
  if (name && !name.toLowerCase().replace(/-/g, '').includes('noreply')) return name;
  const domain = adresse.split('@').pop();
  return domain.includes('.') ? domain.split('.').slice(-2, -1)[0] : (adresse || 'unbekannt');
}

const adresseVon = (absender) => ((/<([^>]+)>/.exec(absender) || [, absender])[1] || '').trim().toLowerCase();

async function baumLaden() {
  const d = await gh(`/repos/${zustand.repo}/git/trees/main?recursive=1`);
  return d.tree.filter((t) => t.type === 'blob').map((t) => t.path);
}

function monateAus(pfade) {
  const monate = new Set([new Date().toISOString().slice(0, 7)]);
  for (const p of pfade) {
    const m = /^(?:notizen\/\d{4}\/[^/]+|eingang)\/(\d{4}-\d{2})-[^/]*\.md$/.exec(p) || /^index\/mail\/(\d{4}-\d{2})\.jsonl$/.exec(p);
    if (m) monate.add(m[1]);
  }
  return [...monate].sort().reverse();
}

async function mailsLaden(monat, pfade) {
  const md = pfade.filter((p) => new RegExp(`^(notizen/\\d{4}/[^/]+|eingang)/${monat}-[^/]*\\.md$`).test(p));
  const notizen = await Promise.all(md.map(async (p) => {
    try { return { art: p.startsWith('eingang/') ? 'eingang' : 'notiz', pfad: p, ...notizLesen((await dateiLesen(p)).text) }; } catch { return null; }
  }));
  const text = await dateiOderLeer(`index/mail/${monat}.jsonl`);
  const index = text.split('\n').filter(Boolean).map((z) => { try { return JSON.parse(z); } catch { return null; } })
    .filter(Boolean).map((z) => ({ art: z.verworfen ? 'verworfen' : 'index', zeile: z }));
  const alle = [...notizen.filter(Boolean), ...index];
  const datum = (m) => String(m.zeile ? m.zeile.datum : m.meta.erstellt);
  return alle.sort((a, b) => datum(b).localeCompare(datum(a)));
}

// --- Eine Mail entscheiden ---------------------------------------------------
// Eine Karte fuer alle Faelle: offene Mail (Eingang), abgelegte Notiz und nur
// gemerkte oder aussortierte Mail (Index). Oben steht, wo die Mail liegt bzw.
// hinkommt, als echter Drive-Pfad mit Link, darunter was genau dorthin kommt.
// Drei Knoepfe fuer den haeufigen Fall, alles andere unter "Mehr".

function jahrWahl(vorgabe, datum) {
  const s = document.createElement('select');
  const jahre = new Set([...Object.keys(zustand.jahre || {}).map(jahrZahl), Number(String(datum).slice(0, 4)), Number(vorgabe)]
    .filter(Boolean));
  for (const j of [...jahre].sort((a, b) => b - a)) {
    s.add(new Option(String(j) + (j === new Date().getFullYear() ? ' (laufendes Jahr)' : ''), String(j), false, j === Number(vorgabe)));
  }
  return s;
}

// "Auch als Kopie in 0000-dauerhaft" mit Unterordner (vorgewaehlt nach Objekt)
function dauerhaftFeld(an, ordner, objekte = []) {
  const box = el('div', 'dauerhaft');
  const l = el('label', 'haken');
  const c = document.createElement('input');
  c.type = 'checkbox'; c.checked = !!an;
  const name = (zustand.dauerhaft && zustand.dauerhaft.name) || '0000-dauerhaft';
  l.append(c, `Auch als Kopie in ${name} (betrifft viele Jahre)`);
  const wahl = document.createElement('select');
  wahl.add(new Option('– Unterordner wählen –', ''));
  const norm = (t) => String(t || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/[^a-z0-9]/g, '');
  const namen = Object.keys(zustand.dauerhaftOrdner || {}).sort((a, b) => a.localeCompare(b, 'de'));
  let vor = typeof ordner === 'string' ? ordner : '';
  if (!vor) {
    for (const o of objekte) {
      const k = norm(o).replace(/^\d+/, '');
      const treffer = namen.find((n) => norm(n).replace(/^\d+/, '').includes(k) || k.includes(norm(n).replace(/^\d+/, '')));
      if (treffer) { vor = treffer; break; }
    }
  }
  for (const n of namen) wahl.add(new Option(n, n, false, n === vor));
  if (vor && !namen.includes(vor)) wahl.add(new Option(`${vor} (neu)`, vor, false, true));
  wahl.add(new Option('➕ Neuer Unterordner …', '+'));
  wahl.hidden = !c.checked;
  c.addEventListener('change', () => { wahl.hidden = !c.checked; box.dispatchEvent(new Event('aenderung', { bubbles: true })); });
  wahl.addEventListener('change', () => {
    if (wahl.value === '+') {
      const neu = (prompt('Name des neuen Unterordners in ' + name) || '').trim();
      if (neu && unterordnerGueltig(neu)) { wahl.add(new Option(`${neu} (neu)`, neu, false, true), wahl.options.length - 1); wahl.value = neu; } else wahl.value = '';
    }
    box.dispatchEvent(new Event('aenderung', { bubbles: true }));
  });
  box.append(l, wahl);
  box.wert = () => (c.checked ? (wahl.value && wahl.value !== '+' ? wahl.value : true) : '');
  box.an = () => c.checked;
  return box;
}

// art: 'eingang' | 'notiz' | 'index' (auch aussortiert); e wie aus eingangLaden/mailsLaden
function entscheidungKarte(e, art, fertig = () => {}) {
  const z = e.zeile;
  const meta = e.meta || {};
  const datum = String(z ? z.datum : meta.erstellt);
  const karte = el('div', 'karte entscheidung');
  karte.append(el('h3', '', z ? (z.betreff || '(ohne Betreff)') : titelVon(e.text)));
  karte.append(el('div', 'hinweis', z ? `${z.datum} · ${z.absender} · ${z.konto}` : `${meta.erstellt} · ${absenderAdresse(e) || 'unbekannt'} · ${meta.quelle}`));

  const v = art === 'eingang' ? meta.vorschlag : null;
  const thema0 = art === 'notiz' ? (meta.themen || [])[0] : '';
  const vorgabe = art === 'notiz'
    ? { thema: thema0, unterordner: unterordnerAusAblage(meta.ablage, thema0), personen: meta.personen, ...notizBezuege(meta),
      jahr: jahrAusAblage(meta.ablage) || Number(datum.slice(0, 4)) }
    : { ...(v && v.thema ? v : {}), jahr: meta.jahr || (v && v.jahr) || Number(datum.slice(0, 4)) };
  const vorschlagJahr = meta.jahr || (v && v.jahr) || null;
  const vorschlagJahrGrund = meta.jahr_grund || (v && v.jahr_grund) || '';

  // Wo es liegt / hinkommt
  const ziel = el('div', 'ziel');
  const zielKopf = el('div', 'ziel-kopf');
  const zielPfad = el('div', 'ziel-pfad');
  const zielInfo = el('div', 'hinweis');
  const jahrHinweis = el('div', 'hinweis jahr-hinweis');
  ziel.append(zielKopf, zielPfad, jahrHinweis, zielInfo);
  const waswo = el('div');
  karte.append(ziel, waswo);

  // Bearbeiten: Ordnersuche und Jahr (bei offener Mail ohne Vorschlag gleich offen)
  const editor = el('div', 'editor');
  const felder = auswahlFelder(vorgabe, z ? { absender: z.absender, betreff: z.betreff, text: z.kurz } : mailKontext(e, v));
  const jahr = jahrWahl(vorgabe.jahr, datum);
  const lj = el('label', '', 'Jahresordner (gehört zu welchem Jahr? Bei Zahlungen das Jahr des Geldflusses)');
  lj.append(jahr);
  editor.append(felder.teile.ordner, lj);
  editor.hidden = !(art === 'eingang' && !(v && v.thema)) && art !== 'index';
  if (z) editor.hidden = true;

  // Mehr
  const mehr = el('details', 'mehr');
  mehr.append(el('summary', '', 'Mehr: Personen, Themen, Steuer, Mail als PDF, Regel …'));
  const pdf = pdfHaken(art === 'notiz' ? !!meta.mail_drive : !!(v && v.mail_drive),
    meta.mail_pdf ? 'Mail als PDF in Drive (Haken weg: PDF kommt in den Ordner „Second Brain Papierkorb“)' : undefined);
  const dauerhaft = dauerhaftFeld(art === 'notiz' ? !!meta.dauerhaft : !!(meta.dauerhaft_vorschlag || (v && v.dauerhaft)),
    meta.dauerhaft, vorgabe.objekte || meta.objekte || []);
  const dauerhaftVorne = !!(meta.dauerhaft || meta.dauerhaft_vorschlag || (v && v.dauerhaft));
  if (meta.dauerhaft_vorschlag && !meta.dauerhaft) dauerhaft.append(el('div', 'hinweis', `Vorschlag: ${meta.dauerhaft_vorschlag}`));
  mehr.append(felder.teile.personen, felder.teile.bezuege, pdf, ...(dauerhaftVorne ? [] : [dauerhaft]));

  const fehler = el('p', 'fehler');
  const knoepfe = el('div', 'knoepfe');
  let bearbeitet = false;
  let haupt = null;
  const wert = () => ({ ...felder.wert(), jahr: Number(jahr.value), mail_drive: pdf.an(), dauerhaft: dauerhaft.wert() });

  const aktualisieren = () => {
    const w = wert();
    const j = Number(jahr.value);
    const uo = unterordnerEinsetzen(w.unterordner, `${j}${datum.slice(4)}`);
    const offen = art === 'eingang' || art === 'index';
    const offenEditor = !editor.hidden;
    zielKopf.textContent = art === 'notiz' && !bearbeitet ? 'Liegt in' : z && !offenEditor ? (z.verworfen ? 'Aussortiert' : 'Nur gemerkt') : offen ? 'Wird abgelegt in' : 'Kommt nach';
    zielPfad.textContent = '';
    if (z && !offenEditor) {
      zielPfad.append(el('span', 'pfad', z.verworfen ? String(z.verworfen) : 'auffindbar, aber nicht abgelegt'));
    } else if (w.thema) {
      const neu = w.unterordner && !ordnerBekannt(w.thema, w.unterordner);
      zielPfad.append(el('span', 'pfad', pfadText(j, w.thema, uo)));
      if (neu) zielPfad.append(el('span', 'neu-marke', 'neuer Ordner'));
      const href = ordnerLink(j, w.thema, uo);
      if (href) zielPfad.append(' ', link('in Drive öffnen', href, 'drive-link'));
    } else {
      zielPfad.append(el('span', 'pfad leer', 'Noch kein Ordner. Tippe unten, um einen zu suchen.'));
    }
    const empfangen = Number(datum.slice(0, 4));
    jahrHinweis.textContent = j !== empfangen
      ? `Gehört zu ${j}, empfangen ${empfangen}${j === vorschlagJahr && vorschlagJahrGrund ? `: ${vorschlagJahrGrund}` : ''}.` : '';
    if (art === 'eingang' && v && v.thema && !bearbeitet) {
      zielInfo.textContent = `Vorschlag, unsicher. ${v.grund || ''}`.trim();
    } else if (art === 'notiz' && !bearbeitet) {
      const durch = String(meta.eingeordnet_durch || '');
      zielInfo.textContent = durch === 'manuell' ? 'Von dir abgelegt.' : durch ? `Automatisch abgelegt (${durch.startsWith('regel/') ? 'Regel ' + durch.slice(6) : durch.startsWith('vertrag/') ? 'Vertrag ' + durch.slice(8) : durch.startsWith('ki/') ? 'KI' : 'gelernt'}${meta.konfidenz && meta.konfidenz < 1 ? ', unsicher' : ''}).` : '';
    } else {
      zielInfo.textContent = bearbeitet && w.thema ? 'Von dir gewählt.' : '';
    }
    waswo.textContent = '';
    const ort = w.thema ? pfadText(j, w.thema, uo) : '';
    if (z && offenEditor) {
      const zeilen = [['📥', 'Anhänge, falls vorhanden,', 'werden aus dem Postfach geholt und kommen nach', '', ''],
        ['📝', 'Text und Zusammenfassung', 'im Second Brain (Notiz)', '', 'hinweis']];
      if (w.mail_drive) zeilen.splice(1, 0, ['✉️', 'Mail als PDF', 'kommt nach', '', '']);
      waswo.append(wasWoListe(zeilen, ort));
    } else if (!z) {
      const plan = art === 'notiz' && !bearbeitet ? null : { mail_drive: w.mail_drive, dauerhaft: w.dauerhaft };
      waswo.append(wasWoListe(wasWo(meta, plan), ort));
    }
    if (haupt) {
      haupt.disabled = !w.thema;
      haupt.textContent = art === 'eingang' ? (bearbeitet ? 'So ablegen' : 'Passt so') : art === 'index' ? 'Ablegen' : 'Speichern';
      haupt.hidden = (art === 'notiz' || !!z) && !offenEditor;
    }
  };
  felder.beiAenderung = () => { bearbeitet = true; aktualisieren(); };
  jahr.addEventListener('change', () => { bearbeitet = true; aktualisieren(); });
  karte.addEventListener('aenderung', () => { bearbeitet = true; aktualisieren(); });
  karte.addEventListener('change', (ev) => { if (mehr.contains(ev.target)) { bearbeitet = true; aktualisieren(); } });

  const tun = (fn) => async () => {
    fehler.textContent = '';
    karte.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    try { await fn(); } catch (err) { fehler.textContent = err.message; }
    karte.querySelectorAll('button').forEach((b) => { b.disabled = false; });
    aktualisieren();
  };
  const speichern = async () => {
    const w = wert();
    const f = auswahlPruefen(w);
    if (f) { fehler.textContent = f; if (editor.hidden) editor.hidden = false; return; }
    if (w.dauerhaft === true) { fehler.textContent = 'Bitte den Unterordner in 0000-dauerhaft wählen.'; return; }
    if (art === 'eingang') {
      await eingangAblegen(e, w, 'manuell', 'aus Eingang abgelegt', undefined, { jahrGrund: w.jahr === vorschlagJahr ? vorschlagJahrGrund : '' });
      if (w.dauerhaft) await abrufStarten();
    } else if (art === 'index') {
      await indexAblegen(e, w);
      await abrufStarten();
    } else {
      const neu = w.mail_drive !== !!meta.mail_drive || w.dauerhaft !== (meta.dauerhaft || '');
      const wie = w.mail_drive && !meta.mail_drive ? 'korrigiert, Mail als PDF für Drive vorgemerkt'
        : !w.mail_drive && meta.mail_drive ? 'korrigiert, Mail-PDF abgewählt' : 'korrigiert';
      await eingangAblegen(e, w, 'manuell', wie, undefined, { jahrGrund: w.jahr === jahrAusAblage(meta.ablage) ? meta.jahr_grund : '' });
      if (neu || meta.drive || meta.mail_pdf) await abrufStarten();
    }
    zustand.alle = null;
    fertig(karte);
  };
  haupt = knopf('Passt so', tun(speichern), '');
  if (art === 'eingang') {
    knoepfe.append(haupt,
      knopf('Anderer Ordner', () => { editor.hidden = !editor.hidden; if (!editor.hidden) felder.teile.suche.focus(); }, 'leise'),
      knopf('Unwichtig', tun(async () => { await eingangVerwerfen(e, false); zustand.alle = null; fertig(karte); }), 'leise'));
  } else if (art === 'notiz') {
    knoepfe.append(knopf('Ändern', (ev) => { editor.hidden = false; ev.target.hidden = true; aktualisieren(); felder.teile.suche.focus(); }, 'leise'), haupt);
  } else if (z.message_id) {
    knoepfe.append(knopf(z.verworfen ? 'Doch ablegen' : 'Ablegen', (ev) => {
      editor.hidden = false; ev.target.hidden = true;
      const oben = felder.vorschlagOben();
      if (oben.thema) felder.setzen(oben);
      mehr.hidden = false;  // Personen, Mail als PDF (oft der Grund: Buchungsbestaetigung)
      aktualisieren(); felder.teile.suche.focus();
    }, 'leise'), haupt);
  } else {
    knoepfe.append(el('span', 'hinweis', 'Ohne Message-ID, kann nicht aus dem Postfach geholt werden.'));
  }
  if (art !== 'index') {
    mehr.append(el('div', 'knoepfe',));
    mehr.lastChild.append(knopf('Regel aus dieser Mail', () => regelAusMail(e, wert()), 'leise klein'));
    if (art === 'eingang') {
      mehr.lastChild.append(knopf('Werbung: Absender immer aussortieren', tun(async () => { await eingangVerwerfen(e, true); zustand.alle = null; fertig(karte); }), 'leise klein'));
    }
    mehr.append(anfordernZeile(e));
  }
  const anzeigen = el('details', 'mail-text');
  anzeigen.append(el('summary', '', 'Mail anzeigen'), el('pre', '', z ? (z.kurz || '') : e.text.replace(/^# .*\n+/, '').split(/\n<!-- ablage -->/)[0]));
  if (z) mehr.hidden = true;
  karte.append(...(dauerhaftVorne ? [dauerhaft] : []), knoepfe, editor, fehler, mehr, anzeigen);
  aktualisieren();
  return karte;
}

// --- Startseite: Suchen und Zu erledigen -----------------------------------

async function zeigeStart() {
  const liste = $('#eingang-liste');
  liste.textContent = 'Lade …';
  let eintraege, laeufe;
  try {
    await stammdatenLaden();
    if (!zustand.regeln) {
      const d = await dateiLesen(REGEL_DATEI);
      zustand.regeln = JSON.parse(d.text);
      zustand.regelSha = d.sha;
    }
    [eintraege, laeufe] = await Promise.all([eingangLaden(), laeufeLaden()]);
  } catch (e) { liste.textContent = ''; melde(e.message, 'fehler'); return; }
  liste.textContent = '';
  $('#offen-zahl').textContent = eintraege.length ? String(eintraege.length) : '';
  if (!eintraege.length) liste.append(el('p', 'gut', 'Nichts zu erledigen. Alles ist abgelegt.'));
  for (const e of eintraege) {
    liste.append(entscheidungKarte(e, 'eingang', (karte) => {
      karte.remove();
      const rest = liste.querySelectorAll('.karte').length;
      $('#offen-zahl').textContent = rest ? String(rest) : '';
      if (!rest) liste.append(el('p', 'gut', 'Nichts zu erledigen. Alles ist abgelegt.'));
    }));
  }
  startStatus(laeufe);
  zeigeDauerhaftFragen(laeufe);
  zeigeVerworfen();
}

async function startStatus(laeufe) {
  const status = $('#ablauf-status');
  const auto = $('#auto-zeile');
  auto.textContent = '';
  try {
    const d = await gh(`/repos/${zustand.repo}/actions/workflows/${MAIL_WORKFLOW}/runs?per_page=1`);
    const l = d.workflow_runs[0];
    if (l) {
      const [text, klasse] = ERGEBNIS[l.conclusion] || [STATUS[l.status] || l.status, ''];
      status.textContent = `Letzter Abruf: ${new Date(l.created_at).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })}, ${text}.`;
      status.className = 'hinweis ' + klasse;
    }
  } catch { /* Status ist nur Beiwerk */ }
  const grenze = Date.now() - 2 * 24 * 3600 * 1000;
  const neu = laeufe.filter((l) => new Date(l.zeit).getTime() >= grenze)
    .flatMap((l) => (l.eintraege || []).filter((x) => x.aktion === 'notiz' && x.durch !== 'manuell'));
  if (neu.length) {
    auto.append(`${neu.length} ${neu.length === 1 ? 'Mail wurde' : 'Mails wurden'} seit gestern automatisch abgelegt. `,
      knopf('Ansehen und prüfen', () => { $('#mails-art').value = 'auto'; merke('sb-mails-monat', ''); $('#mails-monat').value = ''; zeigeReiter('mails'); }, 'leise klein'));
  }
}

// Automatisch abgelegte Dokumente, die viele Jahre betreffen: Kopie nach 0000-dauerhaft?
async function zeigeDauerhaftFragen(laeufe) {
  const bereich = $('#dauerhaft-bereich');
  const liste = $('#dauerhaft-liste');
  liste.textContent = '';
  const kandidaten = [...new Map(laeufe.flatMap((l) => (l.eintraege || []).filter((x) => x.aktion === 'notiz' && x.dauerhaft))
    .map((x) => [x.pfad, x])).values()].slice(0, 10);
  const offen = (await Promise.all(kandidaten.map(async (x) => {
    try { const n = notizLesen((await dateiLesen(x.pfad)).text); return { pfad: x.pfad, ...n }; } catch { return null; }
  }))).filter((n) => n && n.meta.dauerhaft_vorschlag && !n.meta.dauerhaft && !n.meta.dauerhaft_nein);
  bereich.hidden = !offen.length;
  for (const n of offen) {
    const karte = el('div', 'karte');
    karte.append(el('h3', '', titelVon(n.text)), el('div', 'hinweis', `${n.meta.erstellt} · liegt in ${ablageText(n.meta.ablage)} · ${n.meta.dauerhaft_vorschlag}`));
    const feld = dauerhaftFeld(true, '', n.meta.objekte || []);
    feld.querySelector('label').hidden = true;
    const fehler = el('p', 'fehler');
    const merken = async (wert) => {
      await commitMehrere(async () => {
        const akt = notizLesen((await dateiLesen(n.pfad)).text);
        if (wert) akt.meta.dauerhaft = wert; else akt.meta.dauerhaft_nein = true;
        return [{ pfad: n.pfad, text: notizSchreiben(akt.meta, akt.text) }];
      }, `dauerhaft: ${n.meta.id} ${wert ? '-> ' + wert : 'nein'} (Web)`);
    };
    karte.append(feld,
      knopf('Ja, Kopie anlegen', async () => {
        const w = feld.wert();
        if (!w || w === true) { fehler.textContent = 'Bitte den Unterordner wählen.'; return; }
        try { await merken(w); melde(`Kopie nach ${w} vorgemerkt.`, 'gut'); await abrufStarten(); karte.remove(); } catch (e) { fehler.textContent = e.message; }
      }, ''),
      knopf('Nein', async () => { try { await merken(''); karte.remove(); } catch (e) { fehler.textContent = e.message; } }, 'leise'),
      fehler);
    liste.append(karte);
  }
}

// Suche ueber alle Monate: Absender, Betreff, Ordner
async function alleMailsLaden() {
  if (zustand.alle) return zustand.alle;
  zustand.pfade = await baumLaden();
  const monate = monateAus(zustand.pfade);
  const listen = await Promise.all(monate.map((m) => mailsLaden(m, zustand.pfade)));
  zustand.alle = listen.flat();
  return zustand.alle;
}

let suchNummer = 0;
async function suchen() {
  const q = $('#such-feld').value.trim().toLowerCase();
  const ziel = $('#such-ergebnis');
  const nr = ++suchNummer;
  $('#start-inhalt').hidden = q.length >= 2;
  if (q.length < 2) { ziel.textContent = ''; return; }
  ziel.textContent = zustand.alle ? '' : 'Suche in allen Monaten …';
  let alle;
  try { alle = await alleMailsLaden(); } catch (e) { ziel.textContent = e.message; return; }
  if (nr !== suchNummer) return;
  const woerter = q.split(/\s+/);
  const treffer = alle.filter((m) => { const t = mailText(m).toLowerCase(); return woerter.every((w) => t.includes(w)); });
  ziel.textContent = '';
  ziel.append(el('p', 'hinweis', treffer.length ? `${treffer.length} ${treffer.length === 1 ? 'Treffer' : 'Treffer'}${treffer.length > 30 ? ', die neuesten 30' : ''}.` : 'Nichts gefunden.'));
  for (const m of treffer.slice(0, 30)) ziel.append(mailKarte(m));
}

// --- Alle Mails ----------------------------------------------------------------

async function zeigeMails(neu = true) {
  const liste = $('#mails-liste');
  const wahl = $('#mails-monat');
  if (neu) {
    liste.textContent = 'Lade …';
    try {
      await stammdatenLaden();
      if (!zustand.regeln) zustand.regeln = JSON.parse((await dateiLesen(REGEL_DATEI)).text);
      zustand.pfade = await baumLaden();
      const monate = monateAus(zustand.pfade);
      const vorher = wahl.value || lade('sb-mails-monat');
      wahl.textContent = '';
      for (const m of monate) wahl.add(new Option(new Date(m + '-15').toLocaleDateString('de-DE', { month: 'long', year: 'numeric' }), m));
      wahl.value = monate.includes(vorher) ? vorher : monate[0];
      zustand.mails = await mailsLaden(wahl.value, zustand.pfade);
    } catch (e) { liste.textContent = ''; melde(e.message, 'fehler'); return; }
  }
  const art = $('#mails-art').value;
  const suche = $('#mails-suche').value.trim().toLowerCase();
  const inDrive = (m) => m.art === 'notiz' && !!(m.meta.drive || m.meta.mail_pdf || m.meta.mail_drive);
  const auto = (m) => m.art === 'notiz' && m.meta.eingeordnet_durch && m.meta.eingeordnet_durch !== 'manuell';
  const passt = (m) => (!art || m.art === art || (art === 'drive' && inDrive(m)) || (art === 'auto' && auto(m)))
    && (!suche || suche.split(/\s+/).every((w) => mailText(m).toLowerCase().includes(w)));
  const gezeigt = zustand.mails.filter(passt);
  const zahl = (a) => zustand.mails.filter((m) => m.art === a).length;
  $('#mails-zahl').textContent = `${zustand.mails.length} Mails: ${zahl('notiz')} abgelegt (${zustand.mails.filter(inDrive).length} mit Dateien in Drive), ${zahl('eingang')} offen, ${zahl('index')} nur gemerkt, ${zahl('verworfen')} aussortiert.`;
  liste.textContent = '';
  for (const m of gezeigt.slice(0, 200)) liste.append(mailKarte(m));
  if (!gezeigt.length) liste.append(el('p', 'hinweis', 'Keine passenden Mails.'));
}

function mailText(m) {
  if (m.zeile) return `${m.zeile.absender} ${m.zeile.betreff}`;
  const thema = (m.meta.themen || [])[0];
  return `${m.meta.absender || ''} ${titelVon(m.text)} ${ablageText(m.meta.ablage)} ${(zustand.themen[thema] || {}).name || ''} ${(m.meta.anhaenge || []).join(' ')}`;
}

function mailKarte(m) {
  if (m.art === 'eingang') {
    const karte = el('div', 'karte');
    karte.append(el('h3', '', titelVon(m.text)), el('div', 'hinweis', `${m.meta.erstellt} · ${absenderAdresse(m) || 'unbekannt'} · ${m.meta.quelle}`));
    const ort = el('div', 'ziel');
    ort.append(el('div', 'ziel-kopf', 'Offen'), el('div', 'pfad', 'wartet auf deine Entscheidung'));
    karte.append(ort, knopf('Jetzt entscheiden', () => { $('#such-feld').value = ''; zeigeReiter('start'); }, 'leise klein'));
    return karte;
  }
  return entscheidungKarte(m, m.art === 'notiz' ? 'notiz' : 'index', () => zeigeMails());
}


// Indexmail -> Notiz mit Kurzinhalt und nachholen: true; Indexzeile entfaellt.
async function indexAblegen(m, w) {
  const z = m.zeile;
  const basis = `${z.datum}-${slug(absenderKurz(z.absender), 20)}-${slug(z.betreff || '', 40)}`;
  let id = basis;
  for (let n = 2; zustand.pfade.some((p) => p.endsWith(`/${id}.md`)); n++) id = `${basis}-${n}`;
  const meta = { id, erstellt: z.datum, quelle: z.konto, personen: [], themen: [], message_id: z.message_id, absender: adresseVon(z.absender), nachholen: true, ohne_anhang: true };
  const text = `# ${(z.betreff || '').trim() || '(ohne Betreff)'}\n\nVon: ${z.absender}  \nDatum: ${z.datum}\n\n${z.kurz || ''}\n`;
  const index = `index/mail/${z.datum.slice(0, 7)}.jsonl`;
  await eingangAblegen({ pfad: '', meta, text }, w, 'manuell', 'aus dem Index abgelegt', async () => {
    const zeilen = (await dateiOderLeer(index)).split('\n').filter(Boolean)
      .filter((l) => { try { return JSON.parse(l).message_id !== z.message_id; } catch { return true; } });
    return [{ pfad: index, text: zeilen.map((l) => l + '\n').join('') }];
  });
}

async function abrufStarten() {
  await gh(`/repos/${zustand.repo}/actions/workflows/${MAIL_WORKFLOW}/dispatches`, {
    method: 'POST', body: JSON.stringify({ ref: 'main' }),
  });
  melde($('#meldung').textContent + ' Der Abruf ist gestartet und erledigt den Rest in ein paar Minuten.', 'gut');
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
  await zeigeReiter('einrichtung', 'regeln');
  zustand.regelVonMail = e;
  zustand.regelVonVorschlag = null;
  regelFormular(-1, { name, absender: [domain], thema: w.thema, unterordner: w.unterordner, personen: w.personen,
    weitere_themen: w.weitere_themen, objekte: w.objekte, steuer: w.steuer,
    ...(e.meta.ohne_anhang ? { ohne_anhang: true } : {}), ...(w.mail_drive ? { mail_drive: true } : {}) });
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
  const [themen, personen, ordner, wissen, bezuege, vertraege] = await Promise.all([dateiLesen('config/themen.yaml'), dateiLesen('config/personen.yaml'),
    dateiOderLeer(ORDNER_DATEI), dateiOderLeer('config/ablagewissen.yaml'), dateiOderLeer('config/bezuege.yaml'), dateiOderLeer('config/vertraege.yaml')]);
  zustand.vertraege = (jsyaml.load(vertraege) || {}).vertraege || [];
  const b = jsyaml.load(bezuege) || {};
  zustand.objekte = b.objekte || {};
  zustand.steuer = b.steuer || {};
  const t = jsyaml.load(themen.text) || {};
  zustand.themen = t.themen || {};
  zustand.jahre = t.jahre || {};
  zustand.dauerhaft = t.dauerhaft || null;
  zustand.personen = jsyaml.load(personen.text).personen || {};
  const o = jsyaml.load(ordner) || {};
  zustand.ordner = o.ordner || {};
  zustand.ordnerIds = o.ids || {};
  zustand.dauerhaftOrdner = o.dauerhaft || {};
  zustand.wissen = (jsyaml.load(wissen) || {}).eintraege || [];
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
    zelle(z, r.name + (r.ohne_anhang ? ' · auch ohne Anhang' : '') + (r.mail_drive ? ' · Mail als PDF' : ''));
    zelle(z, (r.absender || []).join(', '));
    zelle(z, (r.empfaenger || []).join(', '));
    zelle(z, (r.betreff || []).join(', '));
    zelle(z, pfadText('', r.thema, r.unterordner));
    zelle(z, (r.personen || zustand.regeln.standard_personen || []).map((k) => (zustand.personen[k] || {}).name || k).join(', '));
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
    zelle(z, pfadText('', v.thema, ''));
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
  f.mail_drive.checked = !!r.mail_drive;
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
  const bz = $('#regel-bezuege');
  bz.textContent = '';
  zustand.regelBezuege = bezuegeFelder(r);
  bz.append(zustand.regelBezuege);
  $('#regel-fehler').textContent = '';
  regelPfadZeigen();
  f.hidden = false;
  f.scrollIntoView({ behavior: 'smooth' });
}

function regelPfadZeigen() {
  const f = $('#regel-form');
  const jahr = new Date().getFullYear();
  $('#regel-pfad').textContent = f.thema.value
    ? `Kommt nach: ${pfadText(jahr, f.thema.value, unterordnerEinsetzen(f.unterordner.value, `${jahr}-01-01`))} (Jahresordner nach Zugehörigkeit)` : '';
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
  if (f.mail_drive.checked) regel.mail_drive = true;
  regel.thema = f.thema.value;
  if (f.unterordner.value.trim()) regel.unterordner = f.unterordner.value.trim();
  regel.personen = [...$('#regel-personen').querySelectorAll('input:checked')].map((c) => c.value);
  for (const [feld, werte] of Object.entries(zustand.regelBezuege ? zustand.regelBezuege.werte() : {})) {
    const rein = werte.filter((x) => x !== regel.thema);
    if (rein.length) regel[feld] = rein;
  }
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

// --- Einrichtung -------------------------------------------------------------
// Alles, was man selten braucht, hinter dem Zahnrad. Die Einstellungsdateien
// gibt es als Formulare; den Rohtext nur noch unter "Für Fortgeschrittene".

const VERTRAG_DATEI = 'config/vertraege.yaml';
const PERSONEN_DATEI = 'config/personen.yaml';

function zeigeTeil(name) {
  document.querySelectorAll('#einrichtung .teil').forEach((t) => { t.hidden = t.id !== 'teil-' + name; });
  document.querySelectorAll('#unterreiter button').forEach((b) => b.classList.toggle('aktiv', b.dataset.teil === name));
  merke('sb-teil', name);
  return ({
    regeln: zeigeRegeln,
    vertraege: zeigeVertraege,
    ordner: zeigeOrdner,
    personen: zeigePersonen,
    zugang: () => { driveCodeZeigen(); kontenZeigen(); return zeigeSecrets(); },
    ablaeufe: () => { zeigeLaeufe(); return zeigeAbrufe(); },
    dateien: zeigeDatei,
  })[name]();
}

// Datei mit Kopfkommentar neu schreiben: Kommentar bis zum ersten Schluessel behalten
function mitKopf(alt, daten, schluessel) {
  const i = alt.search(new RegExp(`^${schluessel}:`, 'm'));
  return (i > 0 ? alt.slice(0, i) : '') + jsyaml.dump(daten, { lineWidth: -1, flowLevel: 3 });
}

async function regelnLaden() {
  if (!zustand.regeln) {
    const d = await dateiLesen(REGEL_DATEI);
    zustand.regeln = JSON.parse(d.text);
    zustand.regelSha = d.sha;
  }
}

// Vertraege

async function zeigeVertraege() {
  const liste = $('#vertrag-liste');
  liste.textContent = 'Lade …';
  try { await stammdatenLaden(); await regelnLaden(); } catch (e) { melde(e.message, 'fehler'); return; }
  liste.textContent = '';
  zustand.vertraege.forEach((v, i) => {
    const k = el('div', 'karte zeile');
    const text = el('div');
    text.append(el('strong', '', `${v.nummer}`), ` ${v.name || ''}`, el('div', 'hinweis', `→ ${pfadText('', v.thema, v.unterordner)}`));
    k.append(text, knopf('Ändern', () => vertragFormular(i), 'klein leise'), knopf('Löschen', () => vertragLoeschen(i), 'klein leise'));
    liste.append(k);
  });
  if (!zustand.vertraege.length) liste.append(el('p', 'hinweis', 'Noch keine Verträge.'));
  $('#vertrag-form').hidden = true;
}

function vertragFormular(index) {
  const f = $('#vertrag-form');
  const v = index >= 0 ? zustand.vertraege[index] : {};
  zustand.vertragIndex = index;
  $('#vertrag-form-titel').textContent = index >= 0 ? 'Vertrag ändern' : 'Neuer Vertrag';
  f.nummer.value = v.nummer || '';
  f.name.value = v.name || '';
  f.auch.value = (v.auch || []).join(', ');
  const box = $('#vertrag-ordner');
  box.textContent = '';
  zustand.vertragFelder = auswahlFelder({ thema: v.thema, unterordner: v.unterordner || '', personen: v.personen,
    weitere_themen: v.weitere_themen, objekte: v.objekte, steuer: v.steuer }, { betreff: v.name || '', text: String(v.nummer || '') });
  box.append(zustand.vertragFelder);
  $('#vertrag-fehler').textContent = '';
  f.hidden = false;
  f.scrollIntoView({ behavior: 'smooth' });
}

async function vertragSpeichern(ev) {
  ev.preventDefault();
  const f = $('#vertrag-form');
  const w = zustand.vertragFelder.wert();
  const v = { nummer: f.nummer.value.trim(), name: f.name.value.trim(), thema: w.thema };
  if (!v.nummer || v.nummer.replace(/[^0-9a-z]/gi, '').length < 5) { $('#vertrag-fehler').textContent = 'Die Nummer braucht mindestens 5 Ziffern oder Buchstaben.'; return; }
  if (!(w.thema in zustand.themen)) { $('#vertrag-fehler').textContent = 'Bitte einen Ordner wählen.'; return; }
  if (w.unterordner.trim()) v.unterordner = w.unterordner.trim();
  const auch = f.auch.value.split(',').map((x) => x.trim()).filter(Boolean);
  if (auch.length) v.auch = auch;
  if (w.personen.length && JSON.stringify(w.personen) !== JSON.stringify(zustand.regeln.standard_personen || [])) v.personen = w.personen;
  for (const feld of ['weitere_themen', 'objekte', 'steuer']) {
    const x = (w[feld] || []).filter((t) => t !== w.thema);
    if (x.length) v[feld] = x;
  }
  try {
    await commitMehrere(async () => {
      const alt = await dateiOderLeer(VERTRAG_DATEI);
      const liste = (jsyaml.load(alt) || {}).vertraege || [];
      const i = zustand.vertragIndex;
      if (i >= 0 && liste[i] && String(liste[i].nummer) === String(zustand.vertraege[i].nummer)) liste[i] = v; else liste.push(v);
      return [{ pfad: VERTRAG_DATEI, text: mitKopf(alt, { vertraege: liste }, 'vertraege') }, ...await ordnerMerken(w.thema, w.unterordner)];
    }, `vertraege: ${v.nummer} ${zustand.vertragIndex >= 0 ? 'geändert' : 'neu'} (Web)`);
    melde(`Vertrag ${v.nummer} gespeichert.`, 'gut');
    await zeigeVertraege();
  } catch (e) { $('#vertrag-fehler').textContent = e.message; }
}

async function vertragLoeschen(index) {
  const v = zustand.vertraege[index];
  if (!confirm(`Vertrag ${v.nummer} löschen? Die Ablage in Drive bleibt, nur die Erkennung entfällt.`)) return;
  try {
    await commitMehrere(async () => {
      const alt = await dateiOderLeer(VERTRAG_DATEI);
      const liste = ((jsyaml.load(alt) || {}).vertraege || []).filter((x) => String(x.nummer) !== String(v.nummer));
      return [{ pfad: VERTRAG_DATEI, text: mitKopf(alt, { vertraege: liste }, 'vertraege') }];
    }, `vertraege: ${v.nummer} gelöscht (Web)`);
    melde(`Vertrag ${v.nummer} gelöscht.`, 'gut');
    await zeigeVertraege();
  } catch (e) { melde(e.message, 'fehler'); }
}

// Ordner

async function zeigeOrdner() {
  const baum = $('#ordner-baum');
  baum.textContent = 'Lade …';
  try { await stammdatenLaden(); } catch (e) { melde(e.message, 'fehler'); return; }
  const wahl = $('#ordner-form').thema;
  const vorher = wahl.value;
  wahl.textContent = '';
  for (const [k, t] of Object.entries(zustand.themen)) wahl.add(new Option(t.ablage || t.name || k, k, false, k === vorher));
  baum.textContent = '';
  const jahr = new Date().getFullYear();
  for (const [k, t] of Object.entries(zustand.themen)) {
    const liste = (zustand.ordner[k] || []).map(String);
    const d = el('details', 'themenordner');
    const s = el('summary');
    const href = ordnerLink(jahr, k, '');
    s.append(el('strong', '', t.ablage || k), el('span', 'hinweis', ` ${t.name || ''} · ${liste.length} Unterordner`));
    d.append(s);
    if (href) d.append(link('Themenordner in Drive öffnen', href, 'drive-link'));
    const ul = el('ul', 'ordnerbaum');
    for (const uo of liste) {
      const li = el('li');
      li.style.paddingLeft = `${(uo.split('/').length - 1) * 16}px`;
      const h = ordnerLink(jahr, k, uo);
      li.append(h && zustand.ordnerIds[`${k}/${uo}`] ? link(uo.split('/').pop(), h) : el('span', '', uo.split('/').pop()),
        knopf('Entfernen', () => ordnerEntfernen(k, uo), 'klein leise'));
      ul.append(li);
    }
    d.append(ul);
    baum.append(d);
  }
  const dname = (zustand.dauerhaft && zustand.dauerhaft.name) || '0000-dauerhaft';
  const d = el('details', 'themenordner');
  d.append(el('summary', '', dname));
  if (zustand.dauerhaft) d.append(link(`${dname} in Drive öffnen`, `https://drive.google.com/drive/folders/${zustand.dauerhaft.id}`, 'drive-link'));
  const ul = el('ul', 'ordnerbaum');
  for (const [n, id] of Object.entries(zustand.dauerhaftOrdner || {})) {
    const li = el('li');
    li.append(id ? link(n, `https://drive.google.com/drive/folders/${id}`) : el('span', '', `${n} (neu)`));
    ul.append(li);
  }
  d.append(ul);
  baum.append(d);
}

async function ordnerEintragen(ev) {
  ev.preventDefault();
  const f = $('#ordner-form');
  const uo = f.pfad.value.trim().replace(/^\/+|\/+$/g, '');
  $('#ordner-fehler').textContent = '';
  if (!uo || !unterordnerGueltig(uo)) { $('#ordner-fehler').textContent = 'Bitte einen gültigen Unterordner eingeben (Ebenen mit /).'; return; }
  try {
    await commitMehrere(async () => ordnerMerken(f.thema.value, uo), `ordner: ${f.thema.value}/${uo} eingetragen (Web)`);
    melde(`${pfadText('', f.thema.value, uo)} eingetragen.`, 'gut');
    f.pfad.value = '';
    await zeigeOrdner();
  } catch (e) { $('#ordner-fehler').textContent = e.message; }
}

async function ordnerEntfernen(thema, uo) {
  if (!confirm(`${pfadText('', thema, uo)} aus der Auswahl entfernen? In Drive bleibt der Ordner, wie er ist.`)) return;
  try {
    await commitMehrere(async () => {
      const alt = await dateiOderLeer(ORDNER_DATEI);
      const daten = jsyaml.load(alt) || {};
      daten.ordner[thema] = (daten.ordner[thema] || []).map(String).filter((x) => x !== uo);
      if (daten.ids) delete daten.ids[`${thema}/${uo}`];
      return [{ pfad: ORDNER_DATEI, text: ordnerDateiText(alt, daten) }];
    }, `ordner: ${thema}/${uo} entfernt (Web)`);
    await zeigeOrdner();
  } catch (e) { melde(e.message, 'fehler'); }
}

// Personen

async function zeigePersonen() {
  const liste = $('#personen-liste');
  liste.textContent = 'Lade …';
  try { await stammdatenLaden(); await regelnLaden(); } catch (e) { melde(e.message, 'fehler'); return; }
  liste.textContent = '';
  for (const [k, p] of Object.entries(zustand.personen)) {
    const z = el('div', 'karte zeile');
    const name = document.createElement('input');
    name.value = p.name || k;
    z.append(name, knopf('Umbenennen', () => personSpeichern(k, name.value), 'klein leise'),
      knopf('Entfernen', () => personEntfernen(k), 'klein leise'));
    liste.append(z);
  }
  const std = $('#standard-personen');
  std.textContent = '';
  const h = haekchen('Vorausgewählt', zustand.personen, zustand.regeln.standard_personen || []);
  h.addEventListener('change', async () => {
    try {
      await regelnLaden();
      zustand.regeln.standard_personen = h.werte();
      await regelnSpeichern('regeln: vorausgewählte Personen geändert (Web)');
      await zeigeTeil('personen');
    } catch (e) { $('#personen-fehler').textContent = e.message; }
  });
  std.append(h);
}

async function personenSchreiben(aendern, nachricht) {
  await commitMehrere(async () => {
    const alt = await dateiOderLeer(PERSONEN_DATEI);
    const daten = jsyaml.load(alt) || {};
    daten.personen = daten.personen || {};
    aendern(daten.personen);
    return [{ pfad: PERSONEN_DATEI, text: mitKopf(alt, { personen: daten.personen }, 'personen') }];
  }, nachricht);
  await zeigePersonen();
}

async function personSpeichern(k, name) {
  name = name.trim();
  if (!name) return;
  try { await personenSchreiben((p) => { p[k] = { ...(p[k] || {}), name }; }, `personen: ${k} heißt ${name} (Web)`); melde('Gespeichert.', 'gut'); } catch (e) { $('#personen-fehler').textContent = e.message; }
}

async function personNeu(ev) {
  ev.preventDefault();
  const name = $('#person-form').name.value.trim();
  const k = slug(name, 20);
  if (!name) return;
  if (k in zustand.personen) { $('#personen-fehler').textContent = 'Die Person gibt es schon.'; return; }
  try { await personenSchreiben((p) => { p[k] = { name }; }, `personen: ${name} neu (Web)`); $('#person-form').name.value = ''; } catch (e) { $('#personen-fehler').textContent = e.message; }
}

async function personEntfernen(k) {
  if (!confirm(`${(zustand.personen[k] || {}).name || k} entfernen? Bereits abgelegte Mails behalten die Zuordnung.`)) return;
  try { await personenSchreiben((p) => { delete p[k]; }, `personen: ${k} entfernt (Web)`); } catch (e) { $('#personen-fehler').textContent = e.message; }
}

// Abrufe: was die letzten Abrufe gebracht haben
async function zeigeAbrufe() {
  const tbody = $('#lauf-liste');
  tbody.textContent = '';
  let laeufe = [];
  try { laeufe = await laeufeLaden(); } catch (e) { melde(e.message, 'fehler'); return; }
  for (const l of laeufe.slice(0, 15)) {
    const z = tbody.insertRow();
    zelle(z, new Date(l.zeit).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }));
    zelle(z, l.konto);
    zelle(z, `${l.notiz} abgelegt, ${l.offen} offen, ${l.index} nur gemerkt, ${l.verwerfen} aussortiert`);
  }
  if (!laeufe.length) zelle(tbody.insertRow(), 'Noch keine Abrufe mit neuen Mails.', 'hinweis');
}

// Anmeldung

async function anmelden(e) {
  e.preventDefault();
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
  zeigeReiter(lade('sb-reiter') || 'start');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#reiter button').forEach((b) => b.addEventListener('click', () => zeigeReiter(b.dataset.reiter)));
  document.querySelectorAll('#unterreiter button').forEach((b) => b.addEventListener('click', () => zeigeTeil(b.dataset.teil)));
  let suchTimer = null;
  $('#such-feld').addEventListener('input', () => { clearTimeout(suchTimer); suchTimer = setTimeout(suchen, 250); });
  $('#vertrag-neu').addEventListener('click', async () => { await stammdatenLaden(); await regelnLaden(); vertragFormular(-1); });
  $('#vertrag-abbrechen').addEventListener('click', () => { $('#vertrag-form').hidden = true; });
  $('#vertrag-form').addEventListener('submit', vertragSpeichern);
  $('#ordner-form').addEventListener('submit', ordnerEintragen);
  $('#person-form').addEventListener('submit', personNeu);
  $('#regel-form').thema.addEventListener('change', regelPfadZeigen);
  $('#regel-form').unterordner.addEventListener('input', regelPfadZeigen);
  $('#anmeldung-form').addEventListener('submit', anmelden);
  $('#abmelden').addEventListener('click', abmelden);
  $('#secret-neu-form').addEventListener('submit', weiteresSecretSpeichern);
  $('#secret-neu-bereich').addEventListener('toggle', () => { if ($('#secret-neu-bereich').open) $('#secret-neu-wert').value = ''; });
  $('#drive-code-kopieren').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#drive-code').value); melde('Code kopiert.', 'gut'); } catch {
      $('#drive-code').select(); melde('Bitte markierten Code kopieren.');
    }
  });
  $('#drive-testen').addEventListener('click', driveTesten);
  $('#regel-neu').addEventListener('click', () => regelFormular(-1));
  $('#regel-abbrechen').addEventListener('click', () => { $('#regel-form').hidden = true; zustand.regelVonMail = null; });
  $('#regel-form').addEventListener('submit', regelAbsenden);
  $('#verwerfen-speichern').addEventListener('click', verwerfenSpeichern);
  $('#datei-wahl').addEventListener('change', zeigeDatei);
  $('#datei-speichern').addEventListener('click', dateiSpeichern);
  $('#mail-starten').addEventListener('click', mailStarten);
  $('#mails-monat').addEventListener('change', async () => {
    merke('sb-mails-monat', $('#mails-monat').value);
    $('#mails-liste').textContent = 'Lade …';
    try { zustand.mails = await mailsLaden($('#mails-monat').value, zustand.pfade); } catch (e) { melde(e.message, 'fehler'); }
    zeigeMails(false);
  });
  $('#mails-art').addEventListener('change', () => zeigeMails(false));
  $('#mails-suche').addEventListener('input', () => zeigeMails(false));

  zustand.repo = lade('sb-repo') || $('#repo').value;
  zustand.token = lade('sb-token');
  $('#repo').value = zustand.repo;
  if (zustand.token) starten();
  else $('#anmeldung').hidden = false;
});
