import os

import pytest

from second_brain import daten, drive, mail, notiz as nz

from test_drive import EDV, Fake, abruf, notiz, repo  # noqa: F401 (Fixture)
from test_mail import roh

NID = '2026-10-28-hoster-buchungsbestatigung'


def wie_web_app(repo, rohmail, **felder):
    """Indexmail als Notiz ablegen, wie es der Reiter Mails tut: nur Kurzinhalt."""
    m = mail.mail_aus_bytes(rohmail)
    meta = dict(id=NID, erstellt=m.datum, quelle='gmx', personen=['anna'], themen=['edv'],
                ablage='0-2026/31 EDV/reisen', absender='billing@hoster-beispiel.de',
                eingeordnet_durch='manuell', message_id=m.message_id, **felder)
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', NID + '.md')
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(nz.Notiz(meta=meta, text='# %s\n\nKurz …\n' % m.betreff)))
    return pfad


def holen_aus(*rohmails):
    mails = {mail.mail_aus_bytes(r).message_id: r for r in rohmails}
    return lambda ids: {i: mails[i] for i in ids if i in mails}


BUCHUNG = roh('Hoster <billing@hoster-beispiel.de>', 'Buchungsbestätigung',
              text='Ihre Buchung Nr. 4711 für den 3. Dezember', html=True, anhang='ticket.pdf')


def test_indexmail_wird_mit_vollem_text_und_anhang_nachgeholt(repo, tmp_path):
    wie_web_app(repo, BUCHUNG, nachholen=True)
    assert mail.nachholen(repo, 'gmx', holen_aus(BUCHUNG), str(tmp_path / 'anh')) == (1, 0)
    n = notiz(repo, 'notizen', '2026', 'edv', NID + '.md')
    assert 'nachholen' not in n.meta and n.meta['anhaenge'] == ['ticket.pdf']
    assert 'Buchung Nr. 4711' in n.text and n.text.startswith('# Buchungsbestätigung')
    assert (tmp_path / 'anh' / NID / 'ticket.pdf').exists()
    assert daten.pruefen(repo) == []
    # erledigt: der naechste Lauf fragt das Postfach nicht mehr
    assert mail.nachholen(repo, 'gmx', lambda ids: pytest.fail('holt erneut'), None) == (0, 0)


def test_nicht_mehr_im_postfach_bleibt_beim_kurzinhalt(repo):
    wie_web_app(repo, BUCHUNG, nachholen=True)
    assert mail.nachholen(repo, 'gmx', lambda ids: {}) == (0, 1)
    n = notiz(repo, 'notizen', '2026', 'edv', NID + '.md')
    assert 'nachholen' not in n.meta and 'Postfach' in n.meta['nachholen_fehler']
    assert 'Kurz' in n.text


def test_anderes_konto_wird_nicht_angefragt(repo):
    wie_web_app(repo, BUCHUNG, nachholen=True)
    assert mail.nachholen(repo, 'gmail', lambda ids: pytest.fail('falsches Konto')) == (0, 0)


def test_mail_als_pdf_in_den_themenordner_und_beim_korrigieren_mit(repo, tmp_path):
    anh = str(tmp_path / 'anh')
    wie_web_app(repo, BUCHUNG, nachholen=True, mail_drive=True)
    mail.nachholen(repo, 'gmx', holen_aus(BUCHUNG), anh)
    seite = open(os.path.join(anh, NID, mail.MAIL_SEITE), encoding='utf-8').read()
    assert '<meta charset="utf-8">' in seite and 'Buchung Nr. 4711' in seite
    assert 'Von</th><td>Hoster &lt;billing@hoster-beispiel.de&gt;' in seite
    f = Fake()
    assert drive.abgleichen(repo, f.bruecke, anh) == (1, 0)
    assert [(a['aktion'], a['ordner_id'], a['pfad'], a['name']) for a in f.aufrufe] == [
        ('hochladen', EDV, 'reisen', '2026-10-28 ticket.pdf'),
        ('pdf', EDV, 'reisen', '2026-10-28 Mail Buchungsbestätigung.pdf')]
    assert b'Buchung Nr. 4711' in f.aufrufe[1]['inhalt']
    n = notiz(repo, 'notizen', '2026', 'edv', NID + '.md')
    assert n.meta['mail_pdf'] == n.meta['drive'] == EDV + ':reisen'
    assert daten.pruefen(repo) == []

    # In der Web-App umgehaengt: Anhang und Mail-PDF ziehen mit
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', NID + '.md')
    n.meta['ablage'] = '0-2026/31 EDV/urlaub/2026'
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    f.aufrufe.clear()
    assert drive.abgleichen(repo, f.bruecke) == (0, 1)
    assert [(a['aktion'], a['pfad'], a['name']) for a in f.aufrufe] == [
        ('verschieben', 'urlaub/2026', '2026-10-28 ticket.pdf'),
        ('verschieben', 'urlaub/2026', '2026-10-28 Mail Buchungsbestätigung.pdf')]
    assert notiz(repo, 'notizen', '2026', 'edv', NID + '.md').meta['mail_pdf'] == EDV + ':urlaub/2026'


def test_vorhandene_notiz_als_pdf_auch_wenn_mail_geloescht(repo, tmp_path):
    anh = str(tmp_path / 'anh')
    abruf(repo, tmp_path / 'vorher', roh('Hoster <billing@hoster-beispiel.de>', 'Rechnung',
                                         text='Betrag 12 Euro', anhang='rechnung.pdf'))
    pfad = os.path.join(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md')
    n = notiz(repo, 'notizen', '2026', 'edv', '2026-10-28-hoster-rechnung.md')
    n.meta.update(mail_drive=True, drive=EDV + ':hoster')   # Anhang liegt schon in Drive
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    assert mail.nachholen(repo, 'gmx', lambda ids: {}, anh) == (0, 1)
    seite = open(os.path.join(anh, '2026-10-28-hoster-rechnung', mail.MAIL_SEITE), encoding='utf-8').read()
    assert 'Betrag 12 Euro' in seite
    f = Fake()
    assert drive.abgleichen(repo, f.bruecke, anh) == (1, 0)
    assert [a['aktion'] for a in f.aufrufe] == ['pdf']


def test_alte_bruecke_ohne_pdf_meldet_was_zu_tun_ist(repo, tmp_path):
    anh = str(tmp_path / 'anh')
    wie_web_app(repo, BUCHUNG, mail_drive=True)
    mail.nachholen(repo, 'gmx', holen_aus(BUCHUNG), anh)
    with pytest.raises(drive.DriveFehler, match='neue Version'):
        drive.abgleichen(repo, Fake('Unbekannte Aktion: pdf').bruecke, anh)
    assert 'mail_pdf' not in notiz(repo, 'notizen', '2026', 'edv', NID + '.md').meta


def test_mail_seite_ersetzt_fremden_zeichensatz_und_skripte():
    s = mail.mail_seite('a@b.de', '2026-10-28', 'Flug', '',
                        '<html><head><meta charset="iso-8859-1"></head><body><script>x()</script>'
                        '<img src="cid:logo"><p>Flug LH 123</p></body></html>')
    assert 'iso-8859-1' not in s and '<script' not in s and 'cid:' not in s
    assert s.index('<meta charset="utf-8">') < s.index('Betreff') < s.index('Flug LH 123')


def test_pdf_name_ohne_verbotene_zeichen():
    assert drive.mail_pdf_name({'erstellt': '2026-10-28'}, 'Re: Buchung 12/2026') == \
        '2026-10-28 Mail Re Buchung 12 2026.pdf'


def test_pdf_abgewaehlt_kommt_in_den_papierkorb(repo, tmp_path):
    anh = str(tmp_path / 'anh')
    pfad = wie_web_app(repo, BUCHUNG, mail_drive=True)
    mail.nachholen(repo, 'gmx', holen_aus(BUCHUNG), anh)
    f = Fake()
    drive.abgleichen(repo, f.bruecke, anh)
    n = notiz(repo, 'notizen', '2026', 'edv', NID + '.md')
    del n.meta['mail_drive']                       # in der Web-App abgewaehlt
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write(nz.schreiben(n))
    f.aufrufe.clear()
    assert drive.abgleichen(repo, f.bruecke) == (0, 1)
    assert f.aufrufe == [{'aktion': 'loeschen', 'ordner_id': EDV, 'pfad': 'reisen',
                          'name': '2026-10-28 Mail Buchungsbestätigung.pdf'}]
    assert 'mail_pdf' not in notiz(repo, 'notizen', '2026', 'edv', NID + '.md').meta
