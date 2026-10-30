// Drive-Bruecke fuer Second Brain. Laeuft als Web-App im Google-Konto, das
// die Ablageordner beschreiben darf (Agentenkonto). Der Mail-Abruf schickt
// Anhaenge hierher; die Web-App setzt beim Einrichten den Schluessel ein.
const SCHLUESSEL = '__SCHLUESSEL__';

function doPost(e) {
  try {
    const a = JSON.parse(e.postData.contents);
    if (a.schluessel !== SCHLUESSEL) throw new Error('Schluessel falsch');
    if (!AKTIONEN[a.aktion]) throw new Error('Unbekannte Aktion: ' + a.aktion);
    return antwort(Object.assign({ ok: true }, AKTIONEN[a.aktion](a)));
  } catch (err) {
    return antwort({ ok: false, fehler: String(err && err.message || err) });
  }
}

function antwort(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

// Ordner-ID ('' = Wurzel dieses Kontos) plus Pfad, fehlende Teile optional anlegen.
function ordner(id, pfad, anlegen) {
  let f = id ? DriveApp.getFolderById(id) : DriveApp.getRootFolder();
  for (const teil of String(pfad || '').split('/').filter(String)) {
    const it = f.getFoldersByName(teil);
    if (it.hasNext()) f = it.next();
    else if (anlegen) f = f.createFolder(teil);
    else throw new Error('Ordner fehlt: ' + teil);
  }
  return f;
}

function datei(f, name) {
  const it = f.getFilesByName(name);
  return it.hasNext() ? it.next() : null;
}

const AKTIONEN = {
  pruefen(a) {
    const ich = Session.getEffectiveUser().getEmail();
    return {
      konto: ich,
      ordner: (a.ordner_ids || []).map((id) => {
        try {
          const f = DriveApp.getFolderById(id);
          return { id: id, name: f.getName(), recht: String(f.getAccess(ich)) };
        } catch (err) {
          return { id: id, fehler: String(err && err.message || err) };
        }
      }),
    };
  },
  hochladen(a) {
    const f = ordner(a.ordner_id, a.pfad, true);
    const alt = datei(f, a.name);
    if (alt) return { id: alt.getId(), vorhanden: true };
    const blob = Utilities.newBlob(Utilities.base64Decode(a.inhalt), a.typ || 'application/octet-stream', a.name);
    return { id: f.createFile(blob).getId() };
  },
  verschieben(a) {
    const von = ordner(a.von_id, a.von_pfad, false);
    const d = datei(von, a.name);
    if (!d) throw new Error('Datei fehlt: ' + a.name);
    d.moveTo(ordner(a.ordner_id, a.pfad, true));
    if (a.leeren && !von.getFiles().hasNext() && !von.getFolders().hasNext()) von.setTrashed(true);
    return { id: d.getId() };
  },
};
