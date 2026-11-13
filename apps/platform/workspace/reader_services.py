"""Owner-scoped Reader catalog and the bounded device content API."""
import unicodedata
from django.db import transaction
from django.db.models import Count

from .models import (ReaderBook, ReaderDeviceBook, ReaderPreparedPage,
                     ReaderProgress)

MAX_DEVICE_BOOKS = 6


class ReaderError(ValueError):
    pass


def device_text(value, maximum):
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(character for character in value
                    if not unicodedata.combining(character) and ord(character) < 128)
    return value[:maximum]


def _part_pages(part):
    pages = ReaderPreparedPage.objects.filter(document=part.document)
    if part.page_start:
        pages = pages.filter(source_page__gte=part.page_start, source_page__lte=part.page_end)
    return pages.order_by('screen_index')


def ready(book):
    parts = list(book.parts.select_related('document'))
    return bool(parts) and all(part.document.state == 'ready' and
        part.document.prepared_pages.exists() for part in parts)


def total_pages(book):
    return sum(_part_pages(part).count() for part in book.parts.select_related('document'))


def page_at(book, number):
    if type(number) is not int or number < 1:
        raise ReaderError('Invalid Reader page.')
    remaining = number
    for part in book.parts.select_related('document'):
        pages = _part_pages(part)
        count = pages.count()
        if remaining <= count:
            page = pages[remaining - 1]
            return part, page
        remaining -= count
    raise ReaderError('Reader page is outside this book.')


def assigned(device):
    selections = (ReaderDeviceBook.objects.filter(device=device, book__owner=device.owner)
        .select_related('book', 'book__progress').prefetch_related('book__parts__document')
        .order_by('book__title')[:MAX_DEVICE_BOOKS])
    books = []
    for selection in selections:
        book = selection.book
        if not ready(book):
            continue
        pages = total_pages(book)
        progress = max(1, min(book.progress.page, pages))
        books.append({'id': str(book.pk), 'title': device_text(book.title, 64),
                      'pages': pages, 'progress': progress,
                      'revision': selection.content_revision})
    return books


def selected_book(device, book_id):
    try:
        selection = (ReaderDeviceBook.objects.select_related('book')
            .get(device=device, book_id=book_id, book__owner=device.owner))
    except (ReaderDeviceBook.DoesNotExist, ValueError) as error:
        raise ReaderError('Book is not assigned to this device.') from error
    if not ready(selection.book):
        raise ReaderError('Book preparation is incomplete.')
    return selection.book


def device_page(device, book_id, number):
    book = selected_book(device, book_id)
    total = total_pages(book)
    part, page = page_at(book, number)
    return {'protocol': 1, 'book_id': str(book.pk), 'title': device_text(book.title, 64),
            'part': device_text(part.title, 48), 'page': number, 'pages': total,
            'source_page': page.source_page, 'text': device_text(page.text, 1200)}


def save_progress(device, book_id, number):
    with transaction.atomic():
        book = selected_book(device, book_id)
        total = total_pages(book)
        if type(number) is not int or not 1 <= number <= total:
            raise ReaderError('Reader page is outside this book.')
        progress = ReaderProgress.objects.select_for_update().get(book=book)
        part, _ = page_at(book, number)
        progress.part = part
        progress.page = number
        progress.viewport_offset = 0
        progress.revision += 1
        progress.save()
        return progress
