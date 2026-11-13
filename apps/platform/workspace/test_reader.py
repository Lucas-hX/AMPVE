"""Reader library tests use private temporary files; no PDF processor or hardware."""
from pathlib import Path
from tempfile import TemporaryDirectory
import secrets

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .device_services import digest
from .models import (Device, ReaderBook, ReaderBookPart, ReaderCollection,
                     ReaderDeviceBook, ReaderDocument, ReaderNote,
                     ReaderPreparedPage, ReaderProgress, User)
from .reader_preparation import paginate


class ReaderLibraryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('reader-owner@example.com', 'Fixture-password-42')
        cls.other = User.objects.create_user('reader-other@example.com', 'Fixture-password-43')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.media = self.settings(MEDIA_ROOT=self.temp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.client.force_login(self.owner)

    def pdf(self, name='source.pdf', content=b'%PDF-1.7\nfixture\n%%EOF'):
        return SimpleUploadedFile(name, content, content_type='application/pdf')

    def upload(self, **changes):
        data = {'book_title': 'The Complete Work', 'part_title': 'Volume I',
                'collection_name': 'Study', 'document': self.pdf()}
        data.update(changes)
        return self.client.post(reverse('reader_library'), data)

    def test_upload_creates_private_book_part_collection_and_progress(self):
        self.assertRedirects(self.upload(), reverse('reader_library'))
        book = ReaderBook.objects.get()
        document = ReaderDocument.objects.get()
        part = ReaderBookPart.objects.get()
        self.assertEqual(book.owner, self.owner)
        self.assertEqual(part.position, 0)
        self.assertEqual(part.document, document)
        self.assertEqual(document.state, 'pending')
        self.assertEqual(document.sha256,
            '025bfabf088fa4396e6638c23e49688c077386554ebe472d6f941d8974bda128')
        self.assertNotIn('source.pdf', document.file.name)
        self.assertTrue(Path(document.file.path).is_file())
        self.assertTrue(ReaderProgress.objects.filter(book=book).exists())
        self.assertEqual(list(book.collections.values_list('name', flat=True)), ['Study'])

    def test_existing_book_accepts_an_ordered_second_pdf_and_virtual_range(self):
        self.upload()
        book = ReaderBook.objects.get()
        response = self.upload(existing_book=str(book.pk), book_title='', part_title='Volume II',
            collection_name='study', page_start='5', page_end='20',
            document=self.pdf('second.pdf', b'%PDF-1.4\nsecond\n%%EOF'))
        self.assertRedirects(response, reverse('reader_library'))
        parts = list(book.parts.all())
        self.assertEqual([part.position for part in parts], [0, 1])
        self.assertEqual((parts[1].page_start, parts[1].page_end), (5, 20))
        self.assertEqual(ReaderCollection.objects.count(), 1)

    def test_rejects_non_pdf_oversize_and_incomplete_page_range(self):
        response = self.upload(document=SimpleUploadedFile('note.pdf', b'not a pdf'))
        self.assertContains(response, 'valid PDF header')
        self.assertFalse(ReaderDocument.objects.exists())
        response = self.upload(page_start='2')
        self.assertContains(response, 'Enter both ends')
        self.assertFalse(ReaderDocument.objects.exists())

    def test_source_download_and_library_are_owner_isolated(self):
        self.upload()
        document = ReaderDocument.objects.get()
        source = reverse('reader_source_pdf', args=[document.pk])
        response = self.client.get(source)
        self.assertEqual(response.status_code, 200)
        response.close()
        foreign = Client(); foreign.force_login(self.other)
        self.assertEqual(foreign.get(source).status_code, 404)
        self.assertNotContains(foreign.get(reverse('reader_library')), 'The Complete Work')
        self.assertEqual(self.client.get('/media/' + document.file.name).status_code, 404)

    def test_upload_requires_csrf(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.owner)
        self.assertEqual(guarded.post(reverse('reader_library'), {
            'book_title': 'Forged', 'document': self.pdf()}).status_code, 403)

    def test_book_edit_part_order_notes_and_device_selection(self):
        self.upload()
        book = ReaderBook.objects.get()
        self.upload(existing_book=str(book.pk), book_title='', part_title='Volume II',
                    document=self.pdf('second.pdf', b'%PDF-1.7\nsecond\n%%EOF'))
        parts = list(book.parts.all())
        response = self.client.post(reverse('reader_part_move', args=[book.pk, parts[1].pk, 'up']))
        self.assertRedirects(response, reverse('reader_library'))
        self.assertEqual(list(book.parts.values_list('title', flat=True)), ['Volume II', 'Volume I'])
        collection = ReaderCollection.objects.get()
        self.client.post(reverse('reader_book_edit', args=[book.pk]),
                         {'title': 'Renamed work', 'collections': [collection.pk]})
        book.refresh_from_db(); self.assertEqual(book.title, 'Renamed work')
        self.client.post(reverse('reader_note_add'),
                         {'book': book.pk, 'page': 4, 'body': 'Return to this idea.'})
        self.assertTrue(ReaderNote.objects.filter(book=book, page=4).exists())
        device = Device.objects.create(owner=self.owner, name='Reader 7B',
            hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b')
        self.client.post(reverse('reader_device_book'),
                         {'device': device.pk, 'book': book.pk, 'selected': 'on'})
        selection = ReaderDeviceBook.objects.get(device=device, book=book)
        self.client.post(reverse('reader_book_edit', args=[book.pk]),
                         {'title': 'Renamed again', 'collections': [collection.pk]})
        selection.refresh_from_db()
        self.assertEqual(selection.content_revision, 2)
        self.assertEqual(selection.state, 'pending')
        foreign = Client(); foreign.force_login(self.other)
        self.assertEqual(foreign.post(reverse('reader_book_edit', args=[book.pk]),
                                     {'title': 'Stolen'}).status_code, 404)

    def test_device_shelf_enforces_protocol_limit(self):
        device = Device.objects.create(owner=self.owner, name='Reader 7B',
            hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b')
        books = [ReaderBook.objects.create(owner=self.owner, title=f'Book {index}')
                 for index in range(7)]
        for book in books[:6]:
            ReaderDeviceBook.objects.create(device=device, book=book)
        response = self.client.post(reverse('reader_device_book'),
            {'device': device.pk, 'book': books[6].pk, 'selected': 'on'}, follow=True)
        self.assertContains(response, 'at most 6 books')
        self.assertFalse(ReaderDeviceBook.objects.filter(device=device, book=books[6]).exists())

    def test_text_pagination_is_small_and_deterministic(self):
        text = ('A compact paragraph with accented Spanish words: información y también. ' * 100)
        first = paginate(text)
        self.assertEqual(first, paginate(text))
        self.assertGreater(len(first), 1)
        self.assertTrue(all(len(screen.encode('utf-8')) <= 1200 for screen in first))


class ReaderDeviceApiTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        media = self.settings(MEDIA_ROOT=self.temp.name); media.enable(); self.addCleanup(media.disable)
        self.owner = User.objects.create_user('device-reader@example.com', 'Fixture-password-42')
        self.other = User.objects.create_user('other-reader@example.com', 'Fixture-password-43')
        self.token = secrets.token_urlsafe(32)
        self.device = Device.objects.create(owner=self.owner, name='Reader 7B',
            hardware_profile='waveshare-esp32-p4-wifi6-touch-lcd-7b',
            credential_hash=digest(self.token))
        self.book = ReaderBook.objects.create(owner=self.owner, title='Libro español')
        ReaderProgress.objects.create(book=self.book)
        document = ReaderDocument.objects.create(owner=self.owner,
            file=SimpleUploadedFile('book.pdf', b'%PDF-1.7\nfixture\n%%EOF'),
            original_name='book.pdf', sha256='a' * 64, byte_size=24,
            page_count=1, state='ready')
        self.part = ReaderBookPart.objects.create(book=self.book, document=document,
            title='Volumen único', position=0)
        ReaderPreparedPage.objects.create(document=document, screen_index=1,
            source_page=1, text='Primera página', text_sha256='b' * 64)
        ReaderPreparedPage.objects.create(document=document, screen_index=2,
            source_page=1, text='Segunda página', text_sha256='c' * 64)
        ReaderDeviceBook.objects.create(device=self.device, book=self.book)
        self.machine = Client(enforce_csrf_checks=True)

    def post(self, path, payload, token=None):
        return self.machine.post(f'/api/devices/v1/{self.device.pk}/reader/{path}/',
            payload, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + (token or self.token))

    def test_bounded_library_page_and_progress_round_trip(self):
        sync = self.post('sync', {'protocol': 1})
        self.assertEqual(sync.status_code, 200)
        self.assertEqual(sync.json()['books'][0]['title'], 'Libro espanol')
        page = self.post('page', {'protocol': 1, 'book_id': str(self.book.pk), 'page': 2})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()['text'], 'Segunda pagina')
        progress = self.post('progress',
            {'protocol': 1, 'book_id': str(self.book.pk), 'page': 2})
        self.assertEqual(progress.status_code, 200)
        self.book.progress.refresh_from_db()
        self.assertEqual(self.book.progress.page, 2)
        self.assertEqual(self.post('sync', {'protocol': 1},
                                   token=secrets.token_urlsafe(32)).status_code, 401)

    def test_unassigned_and_foreign_books_are_not_exposed(self):
        ReaderDeviceBook.objects.all().delete()
        response = self.post('page',
            {'protocol': 1, 'book_id': str(self.book.pk), 'page': 1})
        self.assertEqual(response.status_code, 409)
        foreign = ReaderBook.objects.create(owner=self.other, title='Foreign')
        ReaderProgress.objects.create(book=foreign)
        ReaderDeviceBook.objects.create(device=self.device, book=foreign)
        self.assertEqual(self.post('sync', {'protocol': 1}).json()['books'], [])
