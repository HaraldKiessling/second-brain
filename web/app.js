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

function zeigeReiter(name) {
  document.querySelectorAll('.reiter').forEach((s) => { s.hidden = s.id !== name; });
  document.querySelectorAll('#reiter button').forEach((b) => b.classList.toggle('aktiv', b.dataset.reiter === name));
  merke('sb-reiter', name);
  return ({ uebersicht: zeigeUebersicht, eingang: zeigeEingang, mails: zeigeMails, zugang: () => { driveCodeZeigen(); kontenZeigen(); return zeigeSecrets(); }, regeln: zeigeRegeln, dateien: zeigeDatei, ablaeufe: zeigeLaeufe })[name]();
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
    const jahr = '0-' + new Date().getFullYear();
    const ids = Object.values(zustand.themen).map((t) => (t.drive || {})[jahr]).filter(Boolean);
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
  erg.textContent = `Verbunden als ${a.konto}. ${gut.length} von ${a.ordner.length} Themenordnern beschreibbar.`;
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
  for (const [t, liste] of Object.entries(zustand.ordner || {})) for (const uo of liste || []) dazu(t, String(uo), 'Ordnerliste');
  for (const w of zustand.wissen || []) if (w.unterordner) dazu(w.thema, String(w.unterordner), 'Ablagewissen');
  for (const v of zustand.vertraege || []) dazu(v.thema, String(v.unterordner || ''), 'Vertrag');
  for (const r of (zustand.regeln && zustand.regeln.regeln) || []) if (r.unterordner) dazu(r.thema, r.unterordner, 'Regel');
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

function ordnerName(o) {
  const t = zustand.themen[o.thema] || {};
  return [t.name || o.thema, ...String(o.unterordner || '').split('/').filter(Boolean)].join(' / ');
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
  const ordner = document.createElement('select');
  ordner.className = 'ordnerwahl';
  ordner.add(new Option('– Ordner wählen –', ''));
  const rang = ordnerRangliste({ ...kontext, aktuell: !kontext.vorschlag && vorgabe.thema ? vorgabe : null });
  const oben = rang.filter((o) => o.punkte > 0).slice(0, 8);
  const wert = (o) => ordnerSchluessel(o.thema, o.unterordner);
  if (oben.length) {
    const g = document.createElement('optgroup');
    g.label = 'Wahrscheinlich';
    for (const o of oben) g.append(new Option(`${ordnerName(o)}  ·  ${o.gruende.slice(0, 2).join(', ')}`, wert(o)));
    ordner.append(g);
  }
  const reihenfolge = Object.keys(zustand.themen);
  const rest = rang.filter((o) => !oben.includes(o)).sort((a, b) =>
    reihenfolge.indexOf(a.thema) - reihenfolge.indexOf(b.thema) || a.unterordner.localeCompare(b.unterordner, 'de'));
  const g2 = document.createElement('optgroup');
  g2.label = 'Alle Ordner';
  for (const o of rest) {
    const tiefe = o.unterordner ? o.unterordner.split('/').length : 0;
    const name = tiefe ? o.unterordner.split('/').pop() : ordnerName(o);
    g2.append(new Option('   '.repeat(tiefe) + name, wert(o)));
  }
  ordner.append(g2);
  const lo = document.createElement('label'); lo.append('Ordner (wahrscheinlichste oben)', ordner);

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
    const k = ordnerSchluessel(thema.value, uo.value.trim().replace(/^\/+|\/+$/g, ''));
    ordner.value = [...ordner.options].some((o) => o.value === k) ? k : '';
    neu.textContent = thema.value && uo.value.trim() && !ordnerBekannt(thema.value, uo.value.trim())
      ? 'Neuer Ordner: wird beim Ablegen in Drive angelegt.' : '';
  };
  ordner.addEventListener('change', () => {
    if (!ordner.value) return;
    const [t, u] = ordner.value.split('\t');
    thema.value = t; uo.value = u;
    abgleichen();
  });
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
  box.append(lo, reihe, neu, personen, bezuege);
  abgleichen();
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

  const felder = auswahlFelder(v || {}, mailKontext(e, v));
  const pdf = pdfHaken(!!(v && v.mail_drive));
  felder.append(pdf);
  const wertMitPdf = felder.wert;
  felder.wert = () => ({ ...wertMitPdf(), mail_drive: pdf.an() });
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
  karte.append(felder, knoepfe, fehler, anfordernZeile(e), details);
  return karte;
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
async function eingangAblegen(e, w, durch, wie = 'aus Eingang abgelegt', weitere = async () => []) {
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
  meta.ablage = [jahrOrdner(datum), thema.ablage, unterordnerEinsetzen(w.unterordner, datum)].filter(Boolean).join('/');
  meta.eingeordnet_durch = durch;
  if (w.mail_drive) meta.mail_drive = true;
  else if ('mail_drive' in w) delete meta.mail_drive;  // liegt schon ein PDF, raeumt der Abruf es weg
  if (!meta.absender && absenderAdresse(e)) meta.absender = absenderAdresse(e);
  const ziel = `notizen/${datum.slice(0, 4)}/${w.thema}/${meta.id}.md`;
  const heute = new Date().toISOString().slice(0, 10);
  const protokoll = `protokoll/${heute.slice(0, 7)}.md`;
  await commitMehrere(async () => [
    { pfad: ziel, text: notizSchreiben(meta, e.text) },
    ...(e.pfad && ziel !== e.pfad ? [{ pfad: e.pfad, loeschen: true }] : []),
    { pfad: protokoll, text: protokollZeile(await dateiOderLeer(protokoll), heute, durch, `Notiz \`${meta.id}\` ${wie}`) },
    ...await ordnerMerken(w.thema, w.unterordner),
    ...await weitere(),
  ], `${!e.pfad ? 'index' : e.pfad.startsWith('eingang/') ? 'eingang' : 'korrektur'}: ${meta.id} -> ${w.thema} (Web)`);
  melde(`Abgelegt unter ${meta.ablage}.`, 'gut');
  return ziel;
}

// Ein neuer Unterordner kommt beim Ablegen in config/ordner.yaml, damit er
// beim naechsten Mal in der Auswahl steht.
async function ordnerMerken(thema, uo) {
  uo = String(uo || '').trim().replace(/^\/+|\/+$/g, '');
  if (!uo) return [];
  const daten = jsyaml.load(await dateiOderLeer(ORDNER_DATEI)) || {};
  const ordner = daten.ordner || {};
  if ((ordner[thema] || []).map(String).includes(uo)) return [];
  ordner[thema] = [...new Set([...(ordner[thema] || []).map(String), uo])].sort((a, b) => a.localeCompare(b, 'de'));
  zustand.ordner = ordner;
  const kopf = '# Bekannte Unterordner der Drive-Ablage je Thema (Pfad unterhalb des Themenordners,\n'
    + '# Ebenen mit /). Die Web-App bietet sie in der Ordnerauswahl an und ergaenzt neue beim Ablegen.\n';
  return [{ pfad: ORDNER_DATEI, text: kopf + jsyaml.dump({ ordner }, { lineWidth: -1 }) }];
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
    const felder = auswahlFelder({ thema, unterordner: unterordnerAusAblage(e.meta.ablage, thema), personen: e.meta.personen, ...notizBezuege(e.meta) }, mailKontext(e));
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

// Soll-Ort in Drive wie drive.ziel(): "<ordner-id>:<pfad>".
function driveZiel(meta) {
  const t = zustand.themen[(meta.themen || [])[0]] || {};
  const teile = String(meta.ablage || '').split('/');
  const id = (t.drive || {})[teile[0]];
  if (teile.length >= 2 && teile[1] === t.ablage && id) return `${id}:${teile.slice(2).join('/')}`;
  return `:${SAMMELORDNER}/${meta.id}`;
}

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
  const passt = (m) => (!art || m.art === art || (art === 'drive' && inDrive(m))) && (!suche || mailText(m).toLowerCase().includes(suche));
  const gezeigt = zustand.mails.filter(passt);
  const zahl = (a) => zustand.mails.filter((m) => m.art === a).length;
  $('#mails-zahl').textContent = `${zustand.mails.length} Mails: ${zahl('notiz')} Notizen (${zustand.mails.filter(inDrive).length} mit Dateien in Drive), ${zahl('eingang')} im Eingang, ${zahl('index')} nur im Index, ${zahl('verworfen')} verworfen.`;
  liste.textContent = '';
  for (const m of gezeigt.slice(0, 200)) liste.append(mailKarte(m));
  if (!gezeigt.length) { const p = document.createElement('p'); p.className = 'hinweis'; p.textContent = 'Keine passenden Mails.'; liste.append(p); }
}

function mailText(m) {
  return m.zeile ? `${m.zeile.absender} ${m.zeile.betreff}` : `${m.meta.absender || ''} ${titelVon(m.text)}`;
}

function ortText(meta) {
  const thema = (meta.themen || [])[0];
  const t = zustand.themen[thema] || {};
  return [t.name || thema, unterordnerAusAblage(meta.ablage, thema)].filter(Boolean).join(' / ');
}

// Zeilen zum Drive-Stand einer Notiz: [text, klasse]
function driveStand(meta) {
  const soll = driveZiel(meta);
  const zeilen = [];
  if (meta.nachholen) zeilen.push(['Vollständige Mail und Anhänge werden beim nächsten Abruf aus dem Postfach geholt.', 'warn']);
  if (meta.nachholen_fehler) zeilen.push([meta.nachholen_fehler, 'warn']);
  if ((meta.anhaenge || []).length) {
    const n = `${meta.anhaenge.length === 1 ? 'Anhang' : 'Anhänge'} ${meta.anhaenge.join(', ')}`;
    if (!meta.drive) zeilen.push([`${n}: noch nicht in Drive.`, 'warn']);
    else if (meta.drive === soll) zeilen.push([`${n} in Drive.`, 'gut']);
    else zeilen.push([`${n}: werden beim nächsten Abruf verschoben.`, 'warn']);
  }
  if (!meta.mail_drive && meta.mail_pdf) zeilen.push(['Mail als PDF: kommt beim nächsten Abruf in den Ordner „Second Brain Papierkorb“.', 'warn']);
  if (meta.mail_drive) {
    if (!meta.mail_pdf) zeilen.push(['Mail als PDF: wird beim nächsten Abruf in Drive abgelegt.', 'warn']);
    else if (meta.mail_pdf === soll) zeilen.push(['Mail als PDF in Drive.', 'gut']);
    else zeilen.push(['Mail als PDF: wird beim nächsten Abruf verschoben.', 'warn']);
  }
  return zeilen;
}

function mailKarte(m) {
  const karte = document.createElement('div');
  karte.className = 'karte';
  const z = m.zeile;
  const h = document.createElement('h3');
  h.textContent = z ? (z.betreff || '(ohne Betreff)') : titelVon(m.text);
  const info = document.createElement('div');
  info.className = 'hinweis';
  info.textContent = z ? `${z.datum} · ${z.absender} · ${z.konto}`
    : `${m.meta.erstellt} · ${absenderAdresse(m) || 'unbekannt'} · ${m.meta.quelle}`;
  const ort = document.createElement('div');
  ort.className = 'ort';
  const art = document.createElement('span');
  art.className = 'art';
  const was = document.createElement('span');
  ort.append(art, was);
  const zusatz = (text, klasse = 'hinweis') => { const d = document.createElement('span'); d.className = 'hinweis ' + klasse; d.textContent = text; ort.append(d); return d; };
  if (m.art === 'notiz') {
    art.textContent = 'Notiz:';
    was.textContent = ortText(m.meta);
    zusatz(`Drive-Pfad: ${m.meta.ablage || '–'} · eingeordnet: ${m.meta.eingeordnet_durch || '–'}`);
    for (const [text, klasse] of driveStand(m.meta)) zusatz(text, klasse);
    const id = driveZiel(m.meta).split(':')[0];
    if (id) {
      const a = document.createElement('a');
      a.href = `https://drive.google.com/drive/folders/${id}`;
      a.target = '_blank'; a.rel = 'noopener';
      a.textContent = 'Themenordner in Drive öffnen';
      zusatz('').append(a);
    }
  } else if (m.art === 'eingang') {
    art.textContent = 'Im Eingang:';
    was.textContent = 'wartet auf deine Entscheidung';
  } else if (m.art === 'verworfen') {
    art.textContent = 'Verworfen:';
    was.textContent = z.verworfen;
  } else {
    art.textContent = 'Nur im Index:';
    was.textContent = 'auffindbar, aber keine Notiz' + (z.spam ? ` (Spam-Wert ${Math.round(z.spam * 100)} %)` : '');
  }
  karte.append(h, info, ort);

  const fehler = document.createElement('p');
  fehler.className = 'fehler';
  const knoepfe = document.createElement('div');
  if (m.art === 'eingang') knoepfe.append(knopf('Im Eingang ansehen', () => zeigeReiter('eingang'), 'klein leise'));
  else if (m.art === 'notiz') knoepfe.append(knopf('Ablage ändern', () => mailFormular(m, karte, knoepfe, fehler), 'klein'));
  else if (z.message_id) knoepfe.append(knopf('Als Notiz ablegen', () => mailFormular(m, karte, knoepfe, fehler), 'klein'));
  else zusatz('Ohne Message-ID, kann nicht aus dem Postfach geholt werden.');
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = 'Mail anzeigen';
  const pre = document.createElement('pre');
  pre.textContent = z ? z.kurz : m.text.replace(/^# .*\n+/, '');
  details.append(summary, pre);
  karte.append(knoepfe, fehler, details);
  return karte;
}

function mailFormular(m, karte, knoepfe, fehler) {
  knoepfe.hidden = true;
  const form = document.createElement('div');
  form.className = 'mail-form';
  const z = m.zeile;
  const vorgabe = z ? {} : { thema: (m.meta.themen || [])[0], unterordner: unterordnerAusAblage(m.meta.ablage, (m.meta.themen || [])[0]), personen: m.meta.personen, ...notizBezuege(m.meta) };
  const felder = auswahlFelder(vorgabe, z ? { absender: z.absender, betreff: z.betreff, text: z.kurz }
    : mailKontext(m, m.meta.vorschlag));
  const liegt = !!(m.meta && m.meta.mail_pdf);
  const haken = pdfHaken(!!(m.meta && m.meta.mail_drive),
    liegt ? 'Mail als PDF in Drive (Haken weg: PDF kommt in den Ordner „Second Brain Papierkorb“)' : undefined);
  const hinweis = document.createElement('p');
  hinweis.className = 'hinweis';
  hinweis.textContent = z ? 'Der nächste Abruf holt die vollständige Mail mit Anhängen aus dem Postfach. Er wird gleich gestartet.'
    : 'Liegen Anhänge oder das Mail-PDF schon in Drive, verschiebt der nächste Abruf sie in den neuen Ordner.';
  const speichern = knopf('Speichern', async () => {
    fehler.textContent = '';
    const w = { ...felder.wert(), mail_drive: haken.an() };
    const f = auswahlPruefen(w);
    if (f) { fehler.textContent = f; return; }
    speichern.disabled = true;
    try {
      const nachAbruf = z ? true : (w.mail_drive !== !!m.meta.mail_drive) || (m.meta.drive || m.meta.mail_pdf);
      const wie = w.mail_drive && !m.meta.mail_drive ? 'korrigiert, Mail als PDF für Drive vorgemerkt'
        : !w.mail_drive && m.meta.mail_drive ? 'korrigiert, Mail-PDF abgewählt' : 'korrigiert';
      if (z) await indexAblegen(m, w);
      else await eingangAblegen(m, w, 'manuell', wie);
      if (nachAbruf) await abrufStarten();
      await zeigeMails();
    } catch (err) { fehler.textContent = err.message; speichern.disabled = false; }
  }, '');
  const abbrechen = knopf('Abbrechen', () => { form.remove(); knoepfe.hidden = false; }, 'leise');
  const v = !z && m.meta.vorschlag;
  if (v && v.thema) {
    const wahl = document.createElement('div');
    wahl.className = 'hinweis';
    wahl.append('Vorschläge: ');
    for (const a of [v, ...(v.alternativen || [])]) {
      wahl.append(knopf(`${ordnerName(a)} (${Math.round((a.konfidenz || 0) * 100)} %)`, () => felder.setzen(a), 'klein leise'));
    }
    form.append(wahl);
  }
  form.append(felder, haken, hinweis, speichern, abbrechen);
  if (!z) form.append(anfordernZeile(m));
  karte.insertBefore(form, fehler);
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
  await zeigeReiter('regeln');
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
  zustand.themen = jsyaml.load(themen.text).themen || {};
  zustand.personen = jsyaml.load(personen.text).personen || {};
  zustand.ordner = (jsyaml.load(ordner) || {}).ordner || {};
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
  zeigeReiter(lade('sb-reiter') || 'uebersicht');
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#reiter button').forEach((b) => b.addEventListener('click', () => zeigeReiter(b.dataset.reiter)));
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
