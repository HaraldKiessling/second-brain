import base64
import os
import shutil

import pytest
import yaml

from second_brain import daten, drive, mail, notiz as nz

from test_mail import BEISPIEL, HEUTE, roh

EDV = 'ID_EDV_2026'


class Fake:
    """Nimmt die Aufrufe an das Apps-Script entgegen."""

    def __init__(self, fehler=None):
        self.aufrufe, self.fehler = [], fehler

    def __call__(self, daten):
        if self.fehler:
            return {'ok': False, 'fehler': self.fehler}
        daten = dict(daten)
        assert daten.pop('schluessel') == 'geheim'
        if 'inhalt' in daten:
            daten['inhalt'] = base64.b64decode(daten['inhalt'])
        self.aufrufe.append(daten)
        return {'ok': True, 'id': 'f1'}

    @property
    def bruecke(self):
        return drive.Bruecke('https://script.example/exec', 'geheim', senden=self)


@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    pfad = ziel / 'config' / 'themen.yaml'
    t = yaml.safe_load(pfad.read_text(encoding='utf-8'))
    t['themen']['edv']['drive'] = {'0-2026': EDV}
    pfad.write_text(yaml.safe_dump(t, allow_unicode=True), encoding='utf-8')
    return str(ziel)


def abruf(repo, anh, *rohmails):
    ablage = mail.Ablage(repo, 'gmx', anhang_ziel=str(anh), heute=HEUTE)
    mail.verarbeiten([mail.mail_aus_bytes(r) for r in rohmails], ablage, daten.regelwerk(repo))


def notiz(repo, *teile):
    with open(os.path.join(repo, *teile), encoding='utf-8') as fh:
        return nz.lesen(fh.read())


def test_notiz_anhang_geht_in_den_drive_ordner_des_themas(repo, tmp_path):
    f = Fake()
    abruf(repo, tmp_path / 'anh', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung November',
                                      anhang='rechnung.pdf'))
    assert drive.abgleichen(repo, f.bruecke, str(tmp_path / 'anh')) == (1, 0)
    nid = '2026-10-28-hoster-rechnung-november'
    assert f.aufrufe == [{'aktion': 'hochladen', 'ordner_id': EDV, 'pfad': 'hoster',
                          'name': '2026-10-28 rechnung.pdf', 'inhalt': b'%PDF-1.4 test',
                          'typ': 'application/pdf'}]
    n = notiz(repo, 'notizen', '2026', 'edv', nid + '.md')
    assert n.meta['anhaenge'] == ['rechnung.pdf'] and n.meta['drive'] == EDV + ':hoster'
    # zweiter Lauf: nichts mehr zu tun
    assert drive.abgleichen(repo, f.bruecke, str(tmp_path / 'anh')) == (0, 0)
    assert len(f.aufrufe) == 1
    assert daten.pruefen(repo) == []


def test_eingang_erst_in_sammelordner_dann_nach_einordnen_verschoben(repo, tmp_path):
    f = Fake()
    abruf(repo, tmp_path / 'anh', roh('wer@irgendwo.de', 'Vertrag', anhang='vertrag.pdf'))
    drive.abgleichen(repo, f.bruecke, str(tmp_path / 'anh'))
    nid = '2026-10-28-irgendwo-vertrag'
    assert (f.aufrufe[0]['ordner_id'], f.aufrufe[0]['pfad']) == ('', 'Second Brain Eingang/' + nid)
    # Einordnen wie die Web-App: Notiz mit Ablage, Eingang geloescht
    n = notiz(repo, 'eingang', nid + '.md')
    n.meta.update(themen=['edv'], personen=['anna'], ablage='0-2026/31 EDV/vertraege/2026')
    os.makedirs(os.path.join(repo, 'notizen', '2026', 'edv'), exist_ok=True)
    with open(os.path.join(repo, 'notizen', '2026', 'edv', nid + '.md'), 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    os.remove(os.path.join(repo, 'eingang', nid + '.md'))
    f.aufrufe.clear()
    assert drive.abgleichen(repo, f.bruecke) == (0, 1)
    assert f.aufrufe == [{'aktion': 'verschieben', 'von_id': '', 'von_pfad': 'Second Brain Eingang/' + nid,
                          'ordner_id': EDV, 'pfad': 'vertraege/2026',
                          'name': '2026-10-28 vertrag.pdf', 'leeren': True}]
    assert notiz(repo, 'notizen', '2026', 'edv', nid + '.md').meta['drive'] == EDV + ':vertraege/2026'


def test_thema_ohne_drive_id_bleibt_im_sammelordner(repo):
    meta = {'id': 'x', 'themen': ['steuer'], 'ablage': '0-2026/10 Steuer'}
    themen = yaml.safe_load(open(os.path.join(repo, 'config', 'themen.yaml'), encoding='utf-8'))['themen']
    assert drive.ziel(meta, themen) == ':Second Brain Eingang/x'


def test_kleine_bilder_werden_nicht_abgelegt():
    from email.message import EmailMessage
    m = EmailMessage()
    m['From'], m['Subject'] = 'a@b.de', 'Rechnung'
    m['Date'] = 'Wed, 28 Oct 2026 10:00:00 +0100'
    m.set_content('x')
    m.add_attachment(b'x' * 100, maintype='image', subtype='png', filename='logo.png')
    m.add_attachment(b'%PDF', maintype='application', subtype='pdf', filename='r.pdf')
    assert [n for n, _ in mail.mail_aus_bytes(m.as_bytes()).dokumente] == ['r.pdf']


def test_drive_fehler_bricht_nicht_ab_und_wird_gemeldet(repo, tmp_path):
    abruf(repo, tmp_path / 'anh', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung',
                                      anhang='rechnung.pdf'))
    with pytest.raises(drive.DriveFehler):
        drive.abgleichen(repo, Fake('Zugriff verweigert').bruecke, str(tmp_path / 'anh'))
    assert 'drive' not in notiz(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md').meta


def test_bruecke_folgt_der_umleitung_wie_bei_apps_script():
    import http.server
    import json
    import threading

    erhalten = []

    class Server(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            erhalten.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(302)
            self.send_header('Location', '/echo')
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true, "konto": "agent@gmail.com"}')

        def log_message(self, *a):
            pass

    s = http.server.HTTPServer(('127.0.0.1', 0), Server)
    threading.Thread(target=s.handle_request).start()
    threading.Thread(target=s.handle_request).start()
    b = drive.Bruecke('http://127.0.0.1:%d/exec' % s.server_port, 'k')
    assert b.aufruf('pruefen', ordner_ids=['x'])['konto'] == 'agent@gmail.com'
    assert erhalten == [{'aktion': 'pruefen', 'ordner_ids': ['x'], 'schluessel': 'k'}]
    s.server_close()


def test_aeltere_notizen_werden_aus_dem_artefakt_nachgetragen(repo, tmp_path):
    abruf(repo, tmp_path / 'anh', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung',
                                      anhang='rechnung.pdf'))
    nid = '2026-10-28-hoster-rechnung'
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', nid + '.md')
    n = notiz(repo, 'notizen', '2026', 'edv', nid + '.md')
    del n.meta['anhaenge']            # wie vor dem Drive-Upload abgelegt
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    (tmp_path / 'anh' / nid / 'logo.png').write_bytes(b'x' * 100)
    f = Fake()
    assert drive.abgleichen(repo, f.bruecke, str(tmp_path / 'anh')) == (0, 0)
    assert drive.abgleichen(repo, f.bruecke, str(tmp_path / 'anh'), nachtragen=True) == (1, 0)
    assert [a['name'] for a in f.aufrufe] == ['2026-10-28 rechnung.pdf']
    assert notiz(repo, 'notizen', '2026', 'edv', nid + '.md').meta['anhaenge'] == ['rechnung.pdf']
