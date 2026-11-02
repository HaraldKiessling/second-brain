"""Text aus Anhaengen: PDF-Text, sonst Texterkennung (Tesseract).

Der Abruf liest jeden Dokument-Anhang einmal und gibt den Text an Regeln,
KI und Steuer (Betrag, Zahlungsdatum). Enthaelt ein PDF keinen Text (Scan),
werden die ersten Seiten als Bild gerendert (pdftoppm) und mit Tesseract
(deutsch) gelesen. Bilder ab 50 KB gehen direkt an Tesseract. Fehlen die
Programme, bleibt der Text leer: Regeln auf den Anhangtext greifen dann
nicht, alles andere laeuft weiter.

Im GitHub-Lauf installiert mail-abruf.yml poppler-utils und tesseract-ocr-deu.
"""

import os
import shutil
import subprocess
import tempfile

MAX_SEITEN = 5        # Texterkennung nur fuer die ersten Seiten
MAX_ZEICHEN = 20000   # so viel Text je Anhang wird gemerkt
MIN_TEXT = 40         # weniger Zeichen: das PDF gilt als Scan
BILDER = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp')


def _lauf(befehl, eingabe=None, zeit=120):
    try:
        r = subprocess.run(befehl, input=eingabe, capture_output=True, timeout=zeit)
    except (OSError, subprocess.SubprocessError):
        return b''
    return r.stdout if r.returncode == 0 else b''


def verfuegbar():
    return {p: bool(shutil.which(p)) for p in ('pdftotext', 'pdftoppm', 'tesseract')}


def ocr_bild(pfad):
    if not shutil.which('tesseract'):
        return ''
    return _lauf(['tesseract', pfad, '-', '-l', 'deu+eng']).decode('utf-8', 'replace')


def pdf_text(inhalt):
    if not shutil.which('pdftotext'):
        return ''
    return _lauf(['pdftotext', '-layout', '-l', '20', '-', '-'], inhalt).decode('utf-8', 'replace')


def pdf_ocr(inhalt):
    if not (shutil.which('pdftoppm') and shutil.which('tesseract')):
        return ''
    with tempfile.TemporaryDirectory() as verz:
        pdf = os.path.join(verz, 'd.pdf')
        with open(pdf, 'wb') as fh:
            fh.write(inhalt)
        _lauf(['pdftoppm', '-r', '200', '-l', str(MAX_SEITEN), '-png', pdf,
               os.path.join(verz, 's')], zeit=180)
        seiten = sorted(d for d in os.listdir(verz) if d.startswith('s') and d.endswith('.png'))
        return '\n'.join(ocr_bild(os.path.join(verz, s)) for s in seiten)


def text(name, inhalt):
    """(text, art) fuer einen Anhang; art ist 'pdf', 'ocr', 'text' oder ''."""
    endung = os.path.splitext(name or '')[1].lower()
    if endung == '.pdf':
        t = pdf_text(inhalt)
        if len(t.strip()) >= MIN_TEXT:
            return _kuerzen(t), 'pdf'
        t = pdf_ocr(inhalt)
        return (_kuerzen(t), 'ocr') if t.strip() else ('', '')
    if endung in BILDER:
        with tempfile.NamedTemporaryFile(suffix=endung) as fh:
            fh.write(inhalt)
            fh.flush()
            t = ocr_bild(fh.name)
        return (_kuerzen(t), 'ocr') if t.strip() else ('', '')
    if endung in ('.txt', '.csv'):
        return _kuerzen(inhalt.decode('utf-8', 'replace')), 'text'
    return '', ''


def _kuerzen(t):
    t = '\n'.join(z.rstrip() for z in t.splitlines())
    while '\n\n\n' in t:
        t = t.replace('\n\n\n', '\n\n')
    return t.strip()[:MAX_ZEICHEN]


def texte(dokumente):
    """Text aller Dokumente, je Anhang mit Kopfzeile '== <name> =='."""
    teile = []
    for name, inhalt in dokumente:
        t, _ = text(name, inhalt)
        if t:
            teile.append('== %s ==\n%s' % (os.path.basename(name), t))
    return '\n\n'.join(teile)
