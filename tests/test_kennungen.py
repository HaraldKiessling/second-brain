import pytest

from second_brain import kennungen as k


def werte(text):
    return {w for w, _ in k.kennungen(text).values()}


@pytest.mark.parametrize('text, erwartet', [
    ('Vertragsnummer 40-012400000-8\nVersicherte Person', '40-012400000-8'),
    ('Versicherungsnummer: 58 100000 K 006\n', '58 100000 K 006'),
    ('Kundennummer: 300000001 Musterweg 35', '300000001'),
    ('Bei Rückfragen geben Sie bitte an:" A000000001\n', 'A000000001'),
    ('Mitgliedsnr: 76-1000001\n', '76-1000001'),
    ('Kd-Nr. 71700\n', '71700'),
    ('Policennummer: 09000000000000001\n', '09000000000000001'),
    ('Coburg, im Februar 2025 662/500000-C Anhänger', '662/500000-C'),   # ohne Beschriftung, HUK-Form
    ('Kassenzeichen\n\n1142000/GRDABG/3\n', '1142000/GRDABG/3'),
])
def test_kennung_erkannt(text, erwartet):
    assert erwartet in werte(text)


@pytest.mark.parametrize('text', [
    'Datum 10.01.2025 Uhrzeit 08:00',
    'IBAN: DE00 1234 5678 9012 3456 78',
    'Telefon 0911 000000 Telefax 0911/000000',
    'Kundennummer: 110000000 12345 Musterstadt',   # Postleitzahl gehoert nicht dazu
    'Rechnungsbetrag 1.549,00 Euro',
    'Steuer-Nr.: 56 56 000 000',             # doppelt gelesener Text
    'Server 87.106.242.66 Kernel 6.8.0-106',
    'Kd-Nr.\n\n11.04.2025 999999',
    'Ihr Termin 20250619',
])
def test_keine_kennung(text):
    gefunden = werte(text)
    assert not gefunden or gefunden == {'110000000'}


def test_ordner_kennungen_nur_eigene():
    doks = [
        {'ordner': 'a', 'text': 'Vertragsnummer 602/710000-P Nutzer, Steuer-ID 56/000000'},
        {'ordner': 'a', 'text': 'Vertragsnummer 602/710000-P'},
        {'ordner': 'b', 'text': 'Steuer-ID 56/000000'},
        {'ordner': 'c', 'text': 'Steuer-ID 56/000000'},
        {'ordner': 'b', 'text': 'API-Key: sk-1234-567890 Passwort geheim 602/111111-X'},
    ]
    erg = k.ordner_kennungen(doks)
    assert [x['wert'] for x in erg['a']['nummern']] == ['602/710000-P']
    assert erg['a']['nummern'][0]['dokumente'] == 2
    assert erg['b']['nummern'] == []      # Steuer-ID in drei Ordnern, Zugangsdaten nicht gelesen
    assert erg['b']['dokumente'] == 1


def test_domains():
    assert k.domains('E-Mail: dialog-service-center@vorwerk.de www.fitx.de/hilfe latin-groove.deLinks') \
        == {'vorwerk.de', 'fitx.de'}
