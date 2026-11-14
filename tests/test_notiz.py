import datetime

import pytest

from second_brain import notiz as nz

GUELTIG = """---
id: 2026-10-28-test
erstellt: 2026-10-28
quelle: mail
personen: [anna]
themen: [edv]
---

# Test

Inhalt.
"""

KTX = nz.Kontext(personen={'anna', 'ben'}, themen={'edv'})


def test_lesen_und_titel():
    n = nz.lesen(GUELTIG)
    assert n.meta['erstellt'] == datetime.date(2026, 10, 28)
    assert n.titel == 'Test'
    assert nz.pruefen(n, KTX) == []


def test_schreiben_ist_umkehrbar():
    n = nz.lesen(GUELTIG)
    wieder = nz.lesen(nz.schreiben(n))
    assert wieder.meta == n.meta
    assert wieder.text == n.text


def test_ohne_frontmatter():
    with pytest.raises(nz.FormatFehler):
        nz.lesen('# Nur Text\n')


def test_meldet_fehlende_und_unbekannte_felder():
    n = nz.lesen(GUELTIG.replace('quelle: mail\n', '').replace('[anna]', '[carl]'))
    fehler = nz.pruefen(n, KTX)
    assert 'Pflichtfeld fehlt: quelle' in fehler
    assert 'Person unbekannt: carl' in fehler


def test_meldet_ungueltige_id_und_datum():
    n = nz.lesen(GUELTIG.replace('id: 2026-10-28-test', 'id: Mit Leerzeichen')
                 .replace('erstellt: 2026-10-28', 'erstellt: gestern'))
    fehler = nz.pruefen(n, KTX)
    assert any(f.startswith('id nur aus') for f in fehler)
    assert 'erstellt muss ein Datum JJJJ-MM-TT sein' in fehler


def test_eingeordnet_durch():
    n = nz.lesen(GUELTIG.replace('themen: [edv]\n', 'themen: [edv]\neingeordnet_durch: bauchgefuehl\n'))
    assert any('eingeordnet_durch' in f for f in nz.pruefen(n, KTX))
