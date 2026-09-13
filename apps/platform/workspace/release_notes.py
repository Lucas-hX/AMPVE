"""Plain release notes authenticated through the signed review-archive digest."""
from io import BytesIO
import zipfile

NAME='release-notes.txt'
MAX_BYTES=8192


def decode_notes(raw):
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError('Release notes must contain 1–8192 UTF-8 bytes')
    value=raw.decode('utf-8')
    if not value.strip() or any(ord(c)<32 and c not in '\n\r\t' for c in value) or '\x7f' in value:
        raise ValueError('Release notes must be nonempty plain text without control bytes')
    return value


def archived_notes(archive):
    """Caller must verify the archive hash against the signed policy first."""
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        matches=[item for item in bundle.infolist() if item.filename==NAME]
        if not matches:return None
        if len(matches)!=1 or not 1<=matches[0].file_size<=MAX_BYTES:
            raise ValueError('Release notes archive member is ambiguous or oversized')
        with bundle.open(matches[0]) as stream:
            return decode_notes(stream.read(MAX_BYTES+1))
