import pytest

from second_brain import kennungen as k


def werte(text):
    return {w for w, _ in k.kennungen(text).values()}


@pytest.mark.parametrize('text, erwartet', [
    ('Vertragsnummer 40-012450403-8\nVersicherte Person', '40-012450403-8'),
    ('Versicherungsnummer: 58 130667 K 006\n', '58 130667 K 006'),
    ('Kundennummer: 309215162 Kieler Str. 35', '309215162'),
    ('Bei Rückfragen geben Sie bitte an:" A369610645\n', 'A369610645'),
    ('Mitgliedsnr: 76-1054125\n', '76-1054125'),
    ('Kd-Nr. 71754\n', '71754'),
    ('Policennummer: 09000000720343173\n', '09000000720343173'),
    ('Coburg, im Februar 2025 662/586547-C Anhänger', '662/586547-C'),   # ohne Beschriftung, HUK-Form
    ('Kassenzeichen\n\n1142801/GRDABG/3\n', '1142801/GRDABG/3'),
])
def test_kennung_erkannt(text, erwartet):
    assert erwartet in werte(text)


@pytest.mark.parametrize('text', [
    'Datum 10.01.2025 Uhrzeit 08:00',
    'IBAN: DE26 3307 0090 0291 2020 00',
    'Telefon 0911 7434-399 Telefax 0911/974-1387',
    'Kundennummer: 110757412 90766 Fürth',   # Postleitzahl gehoert nicht dazu
    'Rechnungsbetrag 1.549,00 Euro',
    'Steuer-Nr.: 56 56 947 947',             # doppelt gelesener Text
    'Server 87.106.242.66 Kernel 6.8.0-106',
    'Kd-Nr.\n\n11.04.2025 999999',
    'Ihr Termin 20250619',
])
def test_keine_kennung(text):
    gefunden = werte(text)
    assert not gefunden or gefunden == {'110757412'}


def test_ordner_kennungen_nur_eigene():
    doks = [
        {'ordner': 'a', 'text': 'Vertragsnummer 602/718680-P Harald, Steuer-ID 56/947/382006'},
        {'ordner': 'a', 'text': 'Vertragsnummer 602/718680-P'},
        {'ordner': 'b', 'text': 'Steuer-ID 56/947/382006'},
        {'ordner': 'c', 'text': 'Steuer-ID 56/947/382006'},
        {'ordner': 'b', 'text': 'API-Key: sk-1234-567890 Passwort geheim 602/111111-X'},
    ]
    erg = k.ordner_kennungen(doks)
    assert [x['wert'] for x in erg['a']['nummern']] == ['602/718680-P']
    assert erg['a']['nummern'][0]['dokumente'] == 2
    assert erg['b']['nummern'] == []      # Steuer-ID in drei Ordnern, Zugangsdaten nicht gelesen
    assert erg['b']['dokumente'] == 1


def test_domains():
    assert k.domains('E-Mail: dialog-service-center@vorwerk.de www.fitx.de/hilfe latin-groove.deLinks') \
        == {'vorwerk.de', 'fitx.de'}
