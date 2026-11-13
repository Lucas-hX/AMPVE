"""Operator-run PDF-to-text preparation; never runs in a web request."""
import hashlib
import re
import textwrap
import unicodedata

from django.db import transaction

from .models import ReaderDocument, ReaderPreparedPage

SCREEN_COLUMNS = 68
SCREEN_LINES = 13
MAX_TEXT_BYTES = 1200
MAX_SOURCE_PAGES = 4000


def _clean(text):
    text = unicodedata.normalize('NFC', text or '')
    text = ''.join(character if character in '\n\t' or ord(character) >= 32 else ' '
                   for character in text)
    paragraphs = [re.sub(r'[ \t]+', ' ', value).strip()
                  for value in re.split(r'\n\s*\n', text)]
    return '\n\n'.join(value for value in paragraphs if value)


def paginate(text):
    """Create deterministic small screens; no PDF layout is sent to the device."""
    lines = []
    for paragraph in _clean(text).split('\n\n'):
        if lines:
            lines.append('')
        lines.extend(textwrap.wrap(paragraph, width=SCREEN_COLUMNS,
            break_long_words=True, break_on_hyphens=False) or [''])
    if not lines:
        lines = ['[Blank page]']
    result = []
    for offset in range(0, len(lines), SCREEN_LINES):
        screen = '\n'.join(lines[offset:offset + SCREEN_LINES]).strip() or '[Blank page]'
        while len(screen.encode('utf-8')) > MAX_TEXT_BYTES:
            split = max(1, len(screen) // 2)
            result.append(screen[:split].rstrip())
            screen = screen[split:].lstrip()
        result.append(screen)
    return result


def prepare_document(document):
    from pypdf import PdfReader

    with document.file.open('rb') as source:
        reader = PdfReader(source, strict=False)
        source_page_count = len(reader.pages)
        if not 1 <= source_page_count <= MAX_SOURCE_PAGES:
            raise ValueError('page_count')
        prepared = []
        screen_index = 0
        for source_page, page in enumerate(reader.pages, start=1):
            for text in paginate(page.extract_text() or ''):
                screen_index += 1
                prepared.append(ReaderPreparedPage(document=document,
                    screen_index=screen_index, source_page=source_page, text=text,
                    text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
    with transaction.atomic():
        locked = ReaderDocument.objects.select_for_update().get(pk=document.pk)
        locked.prepared_pages.all().delete()
        ReaderPreparedPage.objects.bulk_create(prepared, batch_size=500)
        locked.page_count = source_page_count
        locked.state = 'ready'
        locked.error_code = ''
        locked.save(update_fields=['page_count', 'state', 'error_code'])
    return len(prepared)


def fail_document(document, code='pdf_rejected'):
    ReaderDocument.objects.filter(pk=document.pk).update(state='failed', error_code=code)
