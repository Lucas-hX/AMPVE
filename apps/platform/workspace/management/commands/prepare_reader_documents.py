from django.core.management.base import BaseCommand, CommandError

from workspace.models import ReaderDocument
from workspace.reader_preparation import fail_document, prepare_document


class Command(BaseCommand):
    help = 'Prepare pending private Reader PDFs into deterministic display-sized text.'

    def add_arguments(self, parser):
        parser.add_argument('--document')
        parser.add_argument('--limit', type=int, default=10)

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 100:
            raise CommandError('Limit must be between 1 and 100.')
        documents = ReaderDocument.objects.filter(state__in=['pending', 'failed'])
        if options['document']:
            documents = documents.filter(pk=options['document'])
        documents = list(documents.order_by('created_at')[:options['limit']])
        for document in documents:
            try:
                screens = prepare_document(document)
            except Exception as error:
                fail_document(document)
                self.stderr.write(f'{document.pk}: rejected ({type(error).__name__})')
            else:
                document.refresh_from_db(fields=['page_count'])
                self.stdout.write(self.style.SUCCESS(
                    f'{document.pk}: {document.page_count or "?"} PDF pages, {screens} Reader screens'))
