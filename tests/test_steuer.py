import datetime
import json
import os
import shutil
import subprocess

import pytest

from second_brain import anhangtext, betrag, cli, daten, notiz as nz, steuer

BEISPIEL = os.path.join(os.path.dirname(__file__), '..', 'beispiel-daten')


def pdf_mit_text(text):
    """Kleinstes PDF mit einer Textzeile (Helvetica), ohne Zusatzbibliothek."""
    inhalt = 'BT /F1 12 Tf 50 750 Td (%s) Tj ET' % text
    objekte = ['<< /Type /Catalog /Pages 2 0 R >>',
               '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R '
               '/Resources << /Font << /F1 5 0 R >> >> >>',
               '<< /Length %d >>\nstream\n%s\nendstream' % (len(inhalt), inhalt),
               '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    aus, orte = '%PDF-1.4\n', []
    for i, o in enumerate(objekte, 1):
        orte.append(len(aus))
        aus += '%d 0 obj\n%s\nendobj\n' % (i, o)
    xref = len(aus)
    aus += 'xref\n0 %d\n0000000000 65535 f \n' % (len(objekte) + 1)
    aus += ''.join('%010d 00000 n \n' % o for o in orte)
    aus += 'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objekte) + 1, xref)
    return aus.encode('latin-1')


# --- Betrag ------------------------------------------------------------------

def test_betrag_beschriftet_vor_groesstem():
    text = 'Pos 1  120,00 EUR\nRechnungsbetrag: 99,90 EUR\nIhr Kreditrahmen 5.000,00 €'
    assert betrag.betrag(text) == 99.9


def test_betrag_ohne_beschriftung_der_groesste():
    assert betrag.betrag('Kaffee 3,50 €, Kuchen 4,20 €') == 4.2
    assert betrag.betrag('kein Geld hier') is None


def test_zahlung_und_lohnanteil():
    f = betrag.felder('Gesamtbetrag 1.234,56 EUR', 'Arbeitskosten: 400,00 EUR',
                      'Der Betrag wird am 01.01.2027 abgebucht')
    assert f == {'betrag': 1234.56, 'zahlung': datetime.date(2027, 1, 1), 'lohnanteil': 400.0}


# --- Anhangtext ----------------------------------------------------------------

@pytest.mark.skipif(not anhangtext.verfuegbar()['pdftotext'], reason='pdftotext fehlt')
def test_pdf_text():
    t, art = anhangtext.text('r.pdf', pdf_mit_text('Versicherungsschein 624/220429-P Beitrag 45,00 EUR'))
    assert art == 'pdf' and '624/220429-P' in t


@pytest.mark.skipif(not all(anhangtext.verfuegbar().values()), reason='Tesseract fehlt')
def test_scan_wird_per_texterkennung_gelesen(tmp_path):
    # Text als Bild: PDF rendern, Bild wieder als PDF ohne Textebene
    pdf = tmp_path / 't.pdf'
    pdf.write_bytes(pdf_mit_text('Kundennummer 4711 0815 Rechnungsbetrag 99,00 EUR'))
    subprocess.run(['pdftoppm', '-r', '150', '-png', '-singlefile', str(pdf), str(tmp_path / 'bild')],
                   check=True)
    bild = (tmp_path / 'bild.png').read_bytes()
    t, art = anhangtext.text('scan.png', bild)
    assert art == 'ocr' and '4711' in t and 'Rechnungsbetrag' in t
    assert anhangtext.text('leer.pdf', b'%PDF-1.4 kaputt') == ('', '')


# --- Steuerposten und Uebersicht --------------------------------------------

@pytest.fixture
def repo(tmp_path):
    ziel = tmp_path / 'daten'
    shutil.copytree(BEISPIEL, ziel)
    return str(ziel)


def beleg(repo, nid, jahr, steuer_, betrag_=None, **mehr):
    pfad = os.path.join(repo, 'notizen', str(jahr), 'edv', nid + '.md')
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    meta = {'id': nid, 'erstellt': datetime.date(jahr, 3, 1), 'quelle': 'gmx',
            'personen': ['anna'], 'themen': ['edv'], 'steuer': steuer_}
    if betrag_ is not None:
        meta['betrag'] = betrag_
    meta.update(mehr)
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(nz.Notiz(meta=meta, text='# Beleg %s\n' % nid)))


def test_ordner_posten_erben_unterebenen():
    cfg = {'ordner': {'edv': ['a'], 'edv/hoster': ['b']}}
    assert steuer.ordner_posten(cfg, 'edv', 'hoster/2026') == ['b']
    assert steuer.ordner_posten(cfg, 'edv', 'anders') == ['a']
    assert steuer.ordner_posten(cfg, 'steuer', '') == []


def test_uebersicht_summe_fehlende_und_csv(repo):
    posten = daten.steuerposten(repo)
    beleg(repo, 'a1', 2025, ['anna.n.arbeitsmittel'], 10.0)
    beleg(repo, 'a2', 2025, ['anna.35a.handwerker'], 200.0, lohnanteil=80.0)
    beleg(repo, 'b1', 2026, ['anna.n.arbeitsmittel'], 12.5)
    beleg(repo, 'b2', 2025, ['anna.n.arbeitsmittel'], 7.5, zahlung=datetime.date(2026, 1, 2))
    ueb = steuer.uebersicht(repo, posten)
    n26 = ueb['jahre'][2026]['anna']['N']['anna.n.arbeitsmittel']
    assert n26['summe'] == 20.0 and len(n26['belege']) == 2
    assert ueb['fehlend'][2026]['anna'] == ['anna.35a.handwerker']
    text = steuer.csv(ueb, 2025, posten)
    assert '2025;anna;35a;haus;Handwerkerleistungen (Lohnanteil);2025-03-01;200,00;80,00' in text


def test_cli_steuer_schreibt_dateien(repo, capsys):
    beleg(repo, 'a1', 2026, ['anna.n.arbeitsmittel'], 10.0)
    assert cli.main(['steuer', repo]) == 0
    d = json.load(open(os.path.join(repo, 'steuer', '2026.json'), encoding='utf-8'))
    assert d['personen']['anna']['N']['anna.n.arbeitsmittel']['summe'] == 10.0
    assert 'anna.n.arbeitsmittel' in d['posten']
    assert os.path.exists(os.path.join(repo, 'steuer', '2026.csv'))
