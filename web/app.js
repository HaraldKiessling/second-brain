// Einstellungsseite des Second Brain. Spricht direkt mit der GitHub-API;
// der Token bleibt im localStorage dieses Browsers.

'use strict';

// Bekannte Zugangsdaten. Namen muessen zu den Workflows im Daten-Repo passen.
const SECRETS = [
  { name: 'MAIL_GMX_USER', wofuer: 'GMX: Mail-Adresse' },
  { name: 'MAIL_GMX_PASSWORD', wofuer: 'GMX: App-Passwort für IMAP' },
  { name: 'MAIL_GMAIL_USER', wofuer: 'Gmail: Mail-Adresse' },
  { name: 'MAIL_GMAIL_PASSWORD', wofuer: 'Gmail: App-Passwort (Google-Konto → Sicherheit → App-Passwörter)' },
  { name: 'OPENROUTER_API_KEY', wofuer: 'KI-Einordnen (später)' },
];
const REGEL_DATEI = 'regeln/mail.json';
const MAIL_WORKFLOW = 'mail.yml';

const $ = (sel) => document.querySelector(sel);
const zustand = { repo: '', token: '', themen: {}, personen: {}, regeln: null, regelSha: '', bearbeitet: -1 };

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
  ({ zugang: zeigeSecrets, regeln: zeigeRegeln, dateien: zeigeDatei, ablaeufe: zeigeLaeufe })[name]();
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
    zelle(z, (r.betreff || []).join(', '));
    zelle(z, (zustand.themen[r.thema] || {}).name || r.thema);
    zelle(z, (r.personen || zustand.regeln.standard_personen || []).join(', '));
    const td = z.insertCell();
    td.append(knopf('Ändern', () => regelFormular(i)), knopf('Löschen', () => regelLoeschen(i), 'klein leise'));
  });
  $('#verwerfen').value = (zustand.regeln.verwerfen || []).join('\n');
  $('#regel-form').hidden = true;
}

function regelFormular(index) {
  const f = $('#regel-form');
  const r = index >= 0 ? zustand.regeln.regeln[index] : { personen: zustand.regeln.standard_personen || [] };
  zustand.bearbeitet = index;
  $('#regel-form-titel').textContent = index >= 0 ? 'Regel ändern' : 'Neue Regel';
  f.name.value = r.name || '';
  f.absender.value = (r.absender || []).join(', ');
  f.betreff.value = (r.betreff || []).join(', ');
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
  if (!regel.absender && !regel.betreff) return 'Mindestens Absender oder Betreff angeben.';
  if (!(regel.thema in zustand.themen)) return 'Thema unbekannt.';
  if (!regel.personen || !regel.personen.length) return 'Mindestens eine Person wählen.';
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
  if (liste(f.betreff.value).length) regel.betreff = liste(f.betreff.value);
  regel.thema = f.thema.value;
  if (f.unterordner.value.trim()) regel.unterordner = f.unterordner.value.trim();
  regel.personen = [...$('#regel-personen').querySelectorAll('input:checked')].map((c) => c.value);
  const fehler = regelPruefen(regel, zustand.regeln.regeln, zustand.bearbeitet);
  if (fehler) { $('#regel-fehler').textContent = fehler; return; }
  if (zustand.bearbeitet >= 0) zustand.regeln.regeln[zustand.bearbeitet] = regel;
  else zustand.regeln.regeln.push(regel);
  try {
    await regelnSpeichern(`regeln: ${regel.name} ${zustand.bearbeitet >= 0 ? 'geändert' : 'neu'} (Web)`);
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
  zeigeReiter(lade('sb-reiter') || 'zugang');
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
  $('#regel-abbrechen').addEventListener('click', () => { $('#regel-form').hidden = true; });
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
