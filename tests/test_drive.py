import os
import shutil

import pytest
import yaml

from second_brain import daten, drive, mail, notiz as nz

from test_mail import BEISPIEL, HEUTE, roh

EDV = 'ID_EDV_2026'


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
    aufrufe = []
    abruf(repo, tmp_path / 'anh', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung November',
                                      anhang='rechnung.pdf'))
    assert drive.abgleichen(repo, str(tmp_path / 'anh'), lambda *a: aufrufe.append(a)) == (1, 0)
    nid = '2026-10-28-hoster-rechnung-november'
    assert aufrufe == [('copyto', str(tmp_path / 'anh' / nid / 'rechnung.pdf'),
                        'drive,root_folder_id=%s:hoster/2026-10-28 rechnung.pdf' % EDV)]
    n = notiz(repo, 'notizen', '2026', 'edv', nid + '.md')
    assert n.meta['anhaenge'] == ['rechnung.pdf'] and n.meta['drive'] == EDV + ':hoster'
    # zweiter Lauf: nichts mehr zu tun
    assert drive.abgleichen(repo, str(tmp_path / 'anh'), lambda *a: aufrufe.append(a)) == (0, 0)
    assert daten.pruefen(repo) == []


def test_eingang_erst_in_sammelordner_dann_nach_einordnen_verschoben(repo, tmp_path):
    aufrufe = []
    abruf(repo, tmp_path / 'anh', roh('wer@irgendwo.de', 'Vertrag', anhang='vertrag.pdf'))
    drive.abgleichen(repo, str(tmp_path / 'anh'), lambda *a: aufrufe.append(a))
    nid = '2026-10-28-irgendwo-vertrag'
    assert aufrufe[0][2] == 'drive:Second Brain Eingang/%s/2026-10-28 vertrag.pdf' % nid
    # Einordnen wie die Web-App: Notiz mit Ablage, Eingang geloescht
    n = notiz(repo, 'eingang', nid + '.md')
    n.meta.update(themen=['edv'], personen=['anna'], ablage='0-2026/31 EDV/vertraege/2026')
    os.makedirs(os.path.join(repo, 'notizen', '2026', 'edv'), exist_ok=True)
    with open(os.path.join(repo, 'notizen', '2026', 'edv', nid + '.md'), 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    os.remove(os.path.join(repo, 'eingang', nid + '.md'))
    aufrufe.clear()
    assert drive.abgleichen(repo, None, lambda *a: aufrufe.append(a)) == (0, 1)
    assert aufrufe == [
        ('moveto', 'drive:Second Brain Eingang/%s/2026-10-28 vertrag.pdf' % nid,
         'drive,root_folder_id=%s:vertraege/2026/2026-10-28 vertrag.pdf' % EDV),
        ('rmdir', 'drive:Second Brain Eingang/%s' % nid)]
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
    import subprocess

    def kaputt(*a):
        raise subprocess.CalledProcessError(1, ['rclone', *a])
    abruf(repo, tmp_path / 'anh', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung',
                                      anhang='rechnung.pdf'))
    with pytest.raises(drive.DriveFehler):
        drive.abgleichen(repo, str(tmp_path / 'anh'), kaputt)
    assert 'drive' not in notiz(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md').meta
