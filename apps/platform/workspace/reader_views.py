import hashlib
from pathlib import PurePath

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ReaderUploadForm
from .models import (ReaderBook, ReaderBookPart, ReaderCollection,
                     ReaderCollectionBook, ReaderDocument, ReaderProgress)


def _digest(upload):
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def library(request):
    form = ReaderUploadForm(request.POST or None, request.FILES or None, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['document']
        original_name = PurePath(upload.name.replace('\\', '/')).name[-255:]
        sha256 = _digest(upload)
        stored_file = None
        try:
            with transaction.atomic():
                selected = form.cleaned_data['existing_book']
                if selected:
                    book = get_object_or_404(
                        ReaderBook.objects.select_for_update(), pk=selected.pk, owner=request.user)
                else:
                    book = ReaderBook.objects.create(
                        owner=request.user, title=form.cleaned_data['book_title'].strip())
                    ReaderProgress.objects.create(book=book)

                document = ReaderDocument.objects.create(
                    owner=request.user, file=upload, original_name=original_name,
                    sha256=sha256, byte_size=upload.size)
                stored_file = document.file
                last_position = book.parts.aggregate(value=Max('position'))['value']
                ReaderBookPart.objects.create(
                    book=book, document=document,
                    title=(form.cleaned_data['part_title'].strip() or original_name.rsplit('.', 1)[0]),
                    position=0 if last_position is None else last_position + 1,
                    page_start=form.cleaned_data['page_start'], page_end=form.cleaned_data['page_end'])

                collection_name = form.cleaned_data['collection_name'].strip()
                if collection_name:
                    collection = ReaderCollection.objects.filter(
                        owner=request.user, name__iexact=collection_name).first()
                    if not collection:
                        collection = ReaderCollection.objects.create(
                            owner=request.user, name=collection_name)
                    ReaderCollectionBook.objects.get_or_create(
                        collection=collection, book=book,
                        defaults={'position': collection.books.count()})
        except Exception:
            if stored_file:
                stored_file.delete(save=False)
            raise
        messages.success(
            request,
            f'“{book.title}” is in your library. Device preparation has not run yet.')
        return redirect('reader_library')

    books = ReaderBook.objects.filter(owner=request.user).prefetch_related(
        Prefetch('parts', queryset=ReaderBookPart.objects.select_related('document')),
        'collections')
    collections = ReaderCollection.objects.filter(owner=request.user).prefetch_related('books')
    return render(request, 'workspace/reader_library.html', {
        'section': 'reader', 'title': 'Your Reader library.', 'form': form,
        'books': books, 'collections': collections})


@login_required
@require_GET
def source_pdf(request, pk):
    document = get_object_or_404(ReaderDocument, pk=pk, owner=request.user)
    response = FileResponse(
        document.file.open('rb'), content_type='application/pdf',
        as_attachment=True, filename=document.original_name)
    response['Cache-Control'] = 'private, no-store'
    return response
