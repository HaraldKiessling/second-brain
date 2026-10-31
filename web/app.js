// Einstellungsseite des Second Brain. Spricht direkt mit der GitHub-API;
// der Token bleibt im localStorage dieses Browsers.

'use strict';

// Bekannte Zugangsdaten. Namen muessen zu den Workflows im Daten-Repo passen.
const SECRETS = [
  { name: 'MAIL_GMX_USER', wofuer: 'GMX: Mail-Adresse' },
  { name: 'MAIL_GMX_PASSWORD', wofuer: 'GMX: Passwort für IMAP' },
  { name: 'MAIL_GMAIL_USER', wofuer: 'Gmail: Mail-Adresse' },
  { name: 'MAIL_GMAIL_PASSWORD', wofuer: 'Gmail: App-Passwort (Google-Konto → Sicherheit → App-Passwörter)' },
  { name: 'OPENROUTER_API_KEY', wofuer: 'KI-Einordnen (optional, einschalten in config/einordnen.yaml)' },
  { name: 'DRIVE_SKRIPT_URL', wofuer: 'Google Drive: wird von „Google Drive verbinden“ gesetzt (optional)' },
  { name: 'DRIVE_SCHLUESSEL', wofuer: 'Google Drive: wird von „Google Drive verbinden“ gesetzt' },
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
  const liste = [...SECRETS, ...vorhanden.filter((s) => !SECRETS.some((b) => b.name === s.name)).map((s) => ({ name: s.name, wofuer: '' }))];
  for (const s of liste) {
    const z = tbody.insertRow();
    zelle(z, s.name);
    zelle(z, s.wofuer, 'hinweis');
    const stand = gesetzt.get(s.name);
    zelle(z, stand ? 'gesetzt ' + new Date(stand).toLocaleDateString('de-DE') : 'fehlt', stand ? 'gut' : 'warn');
    z.insertCell().append(knopf(stand ? 'Ändern' : 'Setzen', () => secretBearbeiten(s.name)));
  }
}

// Ein Formular pro Konto mit Nutzername und Passwort, damit der Google
// Passwortmanager beides ausfuellt. Gespeichert wird nur, wo Chrome das
// Passwort nicht schon unter einer anderen Seite kennt (GMX-Passwort liegt
// meist unter gmx.net; doppelt soll es nicht liegen).
const KONTEN = [
  { id: 'gmx', titel: 'GMX', feld: 'Passwort', nutzer: 'MAIL_GMX_USER', passwort: 'MAIL_GMX_PASSWORD', typ: 'email', speichern: false,
    hinweis: 'Ins Passwortfeld tippen und „Andere Passwörter“ wählen, dann den Eintrag von gmx.net nehmen. Nur speichern lassen, wenn es ein eigenes App-Passwort ist.' },
  { id: 'gmail', titel: 'Gmail', feld: 'App-Passwort', nutzer: 'MAIL_GMAIL_USER', passwort: 'MAIL_GMAIL_PASSWORD', typ: 'email', speichern: true,
    hinweis: 'Google zeigt ein App-Passwort nur einmal an. Lass es Chrome nach dem Speichern gleich merken.' },
  { id: 'openrouter', titel: 'OpenRouter', feld: 'Schlüssel', fest: 'OpenRouter', passwort: 'OPENROUTER_API_KEY', speichern: true,
    hinweis: 'Den Schlüssel zeigt OpenRouter nur einmal an. Lass ihn Chrome nach dem Speichern merken.' },
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
  passwort.autocomplete = k.speichern ? 'new-password' : 'current-password';
  const haken = document.createElement('input');
  haken.type = 'checkbox';
  haken.checked = k.speichern;
  const hinweis = document.createElement('p');
  hinweis.className = 'hinweis';
  hinweis.textContent = k.hinweis;
  const knopfSpeichern = document.createElement('button');
  knopfSpeichern.type = 'submit';
  knopfSpeichern.textContent = 'Speichern';
  form.append(h, beschriftet(k.fest ? 'Nutzername' : 'Mail-Adresse', nutzer), beschriftet(k.feld, passwort),
    hinweis, beschriftet('Chrome soll das Passwort speichern', haken, 'haken'), knopfSpeichern);
  form.addEventListener('submit', (e) => { e.preventDefault(); kontoSpeichern(k, form, haken.checked); });
  return form;
}

function beschriftet(text, feld, klasse) {
  const l = document.createElement('label');
  if (klasse) { l.className = klasse; l.append(feld, ' ' + text); } else l.append(text + ' ', feld);
  return l;
}

async function kontoSpeichern(k, form, speichern) {
  const nutzer = form.elements.username;
  const passwort = form.elements.password;
  const adresse = k.fest ? '' : nutzer.value.trim();
  const wert = passwort.value;
  if (!wert && !adresse) { melde('Bitte Adresse oder Passwort eingeben.', 'fehler'); return; }
  if (!speichern) {
    // Feld ersetzen, bevor die Anfrage laeuft: Chrome sieht dann kein
    // erfolgreich abgeschicktes Passwort und bietet kein Speichern an.
    const leer = passwort.cloneNode();
    leer.value = '';
    passwort.replaceWith(leer);
  }
  try {
    melde('Speichere ' + k.titel + ' …');
    if (adresse) await secretSetzen(k.nutzer, adresse);
    if (wert) await secretSetzen(k.passwort, wert);
  } catch (e) { melde(e.message, 'fehler'); return; }
  melde(k.titel + ' gespeichert.', 'gut');
  if (speichern) {
    // Ausblenden nach erfolgreicher Anfrage ist Chromes Zeichen fuer
    // „Anmeldung geklappt“, dann bietet er das Speichern an.
    form.hidden = true;
    const fertig = document.createElement('div');
    fertig.className = 'karte';
    fertig.append(k.titel + ' gespeichert. ', knopf('Erneut ändern', () => { form.remove(); fertig.replaceWith(kontoFormular(k)); }, 'klein'));
    form.after(fertig);
    setTimeout(() => form.remove(), 5000);
  }
  zeigeSecrets();
}

function secretBearbeiten(name) {
  const konto = KONTEN.find((k) => k.nutzer === name || k.passwort === name);
  if (konto) {
    const form = $('#konto-' + konto.id);
    if (form) { form.scrollIntoView({ behavior: 'smooth' }); form.querySelector(name === konto.nutzer ? '[name=username]' : '[name=password]').focus(); }
    return;
  }
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
  karte.append(felder, knoepfe, fehler, details);
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
  meta.themen = [w.thema];
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
    ...await weitere(),
  ], `${!e.pfad ? 'index' : e.pfad.startsWith('eingang/') ? 'eingang' : 'korrektur'}: ${meta.id} -> ${w.thema} (Web)`);
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
  const vorgabe = z ? {} : { thema: (m.meta.themen || [])[0], unterordner: unterordnerAusAblage(m.meta.ablage, (m.meta.themen || [])[0]), personen: m.meta.personen };
  const felder = auswahlFelder(vorgabe);
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
  form.append(felder, haken, hinweis, speichern, abbrechen);
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
