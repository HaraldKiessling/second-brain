import datetime

from second_brain import jahr as jz

MAIL = datetime.date(2026, 12, 10)


def test_beitrag_mit_faelligkeit_im_naechsten_jahr():
    j, grund = jz.zugehoerigkeit('Beitragsrechnung Hausrat', 'Der Beitrag ist fällig am 01.01.2027.', (), MAIL)
    assert j == 2027 and '01.01.2027' in grund


def test_abrechnung_fuer_altes_jahr_mit_nachzahlung_zaehlt_geldfluss():
    text = 'Jahresabrechnung 2026. Die Nachzahlung buchen wir am 15.02.2027 ab.'
    assert jz.zugehoerigkeit('Ihre Abrechnung', text, (), datetime.date(2027, 1, 20))[0] == 2027


def test_abrechnung_ohne_geldfluss_zaehlt_das_betroffene_jahr():
    assert jz.zugehoerigkeit('Jahresabrechnung 2026', 'Anbei Ihre Abrechnung.', (), datetime.date(2027, 1, 20))[0] == 2026


def test_zeitraum_ueber_zwei_jahre_ohne_zahltag_zaehlt_der_beginn():
    text = 'Versicherungszeitraum 01.07.2026 - 30.06.2027'
    assert jz.zugehoerigkeit('Nachtrag', text, (), MAIL)[0] == 2026


def test_nichts_erkennbar():
    assert jz.zugehoerigkeit('Hallo', 'Wie geht es?', (), MAIL) == (None, '')


def test_unplausible_jahre_werden_ignoriert():
    assert jz.zugehoerigkeit('Vertrag seit 1998', 'gültig bis 31.12.2099', (), MAIL)[0] is None


def test_dauerhaft_vermutet():
    assert jz.dauerhaft_vermutet('Ihr Versicherungsschein', '') == 'Versicherungsschein'
    assert jz.dauerhaft_vermutet('Unterlagen', '', ['Kaufvertrag Kieler 37.pdf']) == 'Kaufvertrag'
    assert jz.dauerhaft_vermutet('Rechnung Oktober', 'Danke für Ihren Einkauf') == ''


def test_jahresordner_und_ids_ueberstehen_den_jahreswechsel():
    assert jz.jahr_ordner(2026, datetime.date(2026, 5, 1)) == '0-2026'
    assert jz.jahr_ordner(2026, datetime.date(2027, 5, 1)) == '2026'
    assert jz.ordner_jahr('0-2026') == jz.ordner_jahr('2026') == 2026
    assert jz.ordner_jahr('0000-dauerhaft') is None
    assert jz.drive_id({'0-2026': 'A', '2027': 'B'}, 2026) == 'A'
    assert jz.drive_id({'2026': 'A'}, 2026) == 'A'
