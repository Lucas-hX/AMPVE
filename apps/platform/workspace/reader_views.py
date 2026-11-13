import hashlib
from pathlib import PurePath

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Max, Prefetch
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .deployment_views import firmware_api
from .forms import (ReaderBookForm, ReaderDeviceSelectionForm, ReaderNoteForm,
                    ReaderUploadForm)
from .models import (ReaderBook, ReaderBookPart, ReaderCollection,
                     ReaderCollectionBook, ReaderDeviceBook, ReaderDocument,
                     ReaderProgress)
from . import reader_services


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
                ReaderDeviceBook.objects.filter(book=book).update(
                    content_revision=models.F('content_revision') + 1,
                    state='pending')

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

    books = list(ReaderBook.objects.filter(owner=request.user).prefetch_related(
        Prefetch('parts', queryset=ReaderBookPart.objects.select_related('document')),
        'collections', 'notes'))
    for book in books:
        book.settings_form = ReaderBookForm(instance=book, owner=request.user)
    collections = ReaderCollection.objects.filter(owner=request.user).prefetch_related('books')
    return render(request, 'workspace/reader_library.html', {
        'section': 'reader', 'title': 'Your Reader library.', 'form': form,
        'books': books, 'collections': collections,
        'note_form': ReaderNoteForm(owner=request.user),
        'selection_form': ReaderDeviceSelectionForm(owner=request.user),
        'selections': ReaderDeviceBook.objects.filter(device__owner=request.user)
            .select_related('device', 'book')})


@login_required
@require_GET
def source_pdf(request, pk):
    document = get_object_or_404(ReaderDocument, pk=pk, owner=request.user)
    response = FileResponse(
        document.file.open('rb'), content_type='application/pdf',
        as_attachment=True, filename=document.original_name)
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_POST
def edit_book(request, pk):
    book = get_object_or_404(ReaderBook, pk=pk, owner=request.user)
    form = ReaderBookForm(request.POST, instance=book, owner=request.user)
    if form.is_valid():
        form.save()
        if form.changed_data:
            ReaderDeviceBook.objects.filter(book=book).update(
                content_revision=models.F('content_revision') + 1,
                state='pending')
        messages.success(request, 'Book details updated.')
    else:
        messages.error(request, 'Book details were not valid.')
    return redirect('reader_library')


@login_required
@require_POST
def move_part(request, pk, part_id, direction):
    if direction not in {'up', 'down'}:
        return redirect('reader_library')
    with transaction.atomic():
        book = get_object_or_404(
            ReaderBook.objects.select_for_update(), pk=pk, owner=request.user)
        parts = list(book.parts.select_for_update().order_by('position', 'id'))
        current = next((index for index, part in enumerate(parts)
                        if str(part.pk) == str(part_id)), None)
        target = current + (-1 if direction == 'up' else 1) if current is not None else -1
        if current is not None and 0 <= target < len(parts):
            first, second = parts[current], parts[target]
            original_first, original_second = first.position, second.position
            temporary = max(part.position for part in parts) + 1
            first.position = temporary; first.save(update_fields=['position'])
            # The temporary value avoids the unique constraint while positions are swapped.
            second.position = original_first; second.save(update_fields=['position'])
            first.position = original_second; first.save(update_fields=['position'])
            ReaderDeviceBook.objects.filter(book=book).update(
                content_revision=models.F('content_revision') + 1,
                state='pending')
            messages.success(request, 'Book parts reordered.')
    return redirect('reader_library')


@login_required
@require_POST
def add_note(request):
    form = ReaderNoteForm(request.POST, owner=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, 'Reading note saved.')
    else:
        messages.error(request, 'The reading note was not valid.')
    return redirect('reader_library')


@login_required
@require_POST
def select_device_book(request):
    form = ReaderDeviceSelectionForm(request.POST, owner=request.user)
    if form.is_valid():
        if form.cleaned_data['selected']:
            ReaderDeviceBook.objects.get_or_create(
                device=form.cleaned_data['device'], book=form.cleaned_data['book'])
            messages.success(request, 'Book added to the device shelf.')
        else:
            ReaderDeviceBook.objects.filter(
                device=form.cleaned_data['device'], book=form.cleaned_data['book']).delete()
            messages.success(request, 'Book removed from the device shelf.')
    else:
        errors = ' '.join(str(error) for values in form.errors.values() for error in values)
        messages.error(request, errors or 'The device selection was not valid.')
    return redirect('reader_library')


@firmware_api
def device_sync(request, data, device):
    if data != {'protocol': 1}:
        return JsonResponse({'error': 'Invalid Reader sync request.'}, status=400)
    return JsonResponse({'protocol': 1, 'books': reader_services.assigned(device)})


@firmware_api
def device_page(request, data, device):
    if set(data) != {'protocol', 'book_id', 'page'} or data['protocol'] != 1:
        return JsonResponse({'error': 'Invalid Reader page request.'}, status=400)
    try:
        payload = reader_services.device_page(device, data['book_id'], data['page'])
    except reader_services.ReaderError as error:
        return JsonResponse({'error': str(error)}, status=409)
    return JsonResponse(payload)


@firmware_api
def device_progress(request, data, device):
    if set(data) != {'protocol', 'book_id', 'page'} or data['protocol'] != 1:
        return JsonResponse({'error': 'Invalid Reader progress request.'}, status=400)
    try:
        progress = reader_services.save_progress(device, data['book_id'], data['page'])
    except reader_services.ReaderError as error:
        return JsonResponse({'error': str(error)}, status=409)
    return JsonResponse({'protocol': 1, 'revision': progress.revision})
