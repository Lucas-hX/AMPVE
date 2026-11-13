"""Reader library tests use private temporary files; no PDF processor or hardware."""
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import (ReaderBook, ReaderBookPart, ReaderCollection,
                     ReaderDocument, ReaderProgress, User)


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
