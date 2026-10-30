import os
import shutil

from second_brain import cli, daten

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')


def test_beispiel_daten_sind_gueltig():
    assert daten.pruefen(BEISPIEL) == []


def test_doppelte_id_und_falsche_regel(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    quelle = ziel / 'notizen' / '2026' / 'edv' / '2026-10-28-hoster-rechnung-oktober.md'
    shutil.copy(quelle, quelle.with_name('kopie.md'))
    regel = ziel / 'regeln' / 'mail.json'
    regel.write_text(regel.read_text().replace('"thema": "steuer"', '"thema": "gibtsnicht"'))
    meldungen = [m for _, m in daten.pruefen(str(ziel))]
    assert any(m.startswith('id doppelt') for m in meldungen)
    assert 'Regel finanzamt: Thema unbekannt: gibtsnicht' in meldungen


def test_cli_pruefen(capsys):
    assert cli.main(['pruefen', BEISPIEL]) == 0
    assert '1 Notizen geprueft, 0 Fehler' in capsys.readouterr().out
