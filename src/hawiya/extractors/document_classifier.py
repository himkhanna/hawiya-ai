"""Document type classification.

**Phase 1 honest disclosure:** any valid image is treated as a
``PASSPORT``. We don't yet have visual cues (logos, format detection) to
reliably tell a passport from an Emirates ID or GCC ID without first
running an extractor. Phase 2 adds a visual classifier (PaddleOCR + a
small image model). Until then, the classifier's job is to:

1. Reject bytes that aren't a recognisable supported format.
2. Tag the input as ``PASSPORT`` so the MRZ pipeline can run.

If the OCR adapter then fails to find an MRZ, we surface
``DOCUMENT_UNREADABLE`` to the consumer, who decides whether to retry
or escalate to manual entry.

**Formats supported in Phase 1:** JPEG, PNG, TIFF.

**Formats deliberately rejected** (clearer error than letting OCR fail):
- PDF — needs a rasterisation pre-step (pdf2image); planned for Phase 2
  alongside multi-document submission. For now, send the photo page as
  an image.
- HEIC / HEIF — iPhone default since iOS 11. Pillow doesn't decode it
  without the optional pillow-heif plugin; planned alongside the
  capture-device pilot in BUILD_PLAN week 5.
"""

from __future__ import annotations

from hawiya.extractors.types import DocumentType

# Magic byte prefixes for the formats we accept.
_ACCEPTED_PREFIXES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"II*\x00": "image/tiff",  # little-endian TIFF
    b"MM\x00*": "image/tiff",  # big-endian TIFF
}

# Magic byte prefixes for formats we explicitly recognise but cannot yet
# process. Detected so we can return a helpful message rather than the
# generic "unrecognised file format".
_REJECTED_PREFIXES: dict[bytes, tuple[str, str]] = {
    b"%PDF-": (
        "application/pdf",
        "PDF documents aren't supported yet — send the photo page as a "
        "JPEG or PNG. PDF rasterisation is on the Phase 2 roadmap.",
    ),
}

# HEIC/HEIF magic is `ftypheic` / `ftypheix` / `ftypmif1` / `ftypheim`
# / `ftypheis` at bytes 4-12. We detect by sniffing the brand at
# offset 4.
_HEIC_BRANDS: frozenset[bytes] = frozenset(
    {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1", b"heif"}
)

_MAGIC_PROBE_LEN = 12
_HEIC_BRAND_OFFSET = 8
_HEIC_BRAND_END = 12


class UnsupportedDocumentError(ValueError):
    """The bytes don't look like a supported image format."""


def detect_format(payload: bytes) -> str | None:
    """Return the MIME type sniffed from magic bytes, or None."""
    head = payload[:_MAGIC_PROBE_LEN]
    for prefix, mime in _ACCEPTED_PREFIXES.items():
        if head.startswith(prefix):
            return mime
    if _is_heic(head):
        return "image/heic"
    for prefix, (mime, _msg) in _REJECTED_PREFIXES.items():
        if head.startswith(prefix):
            return mime
    return None


def _is_heic(head: bytes) -> bool:
    # HEIC files begin with ftyp box: size(4) + 'ftyp'(4) + brand(4) + ...
    return (
        len(head) >= _HEIC_BRAND_END
        and head[4:8] == b"ftyp"
        and head[_HEIC_BRAND_OFFSET:_HEIC_BRAND_END] in _HEIC_BRANDS
    )


def classify(payload: bytes, declared_content_type: str | None = None) -> DocumentType:
    """Classify the upload. Phase 1 returns ``PASSPORT`` for any valid input.

    Raises ``UnsupportedDocumentError`` with a human-readable message for
    files in formats we recognise but don't yet process (PDF, HEIC) and
    for completely-unknown bytes.
    """
    if not payload:
        raise UnsupportedDocumentError("empty payload")

    head = payload[:_MAGIC_PROBE_LEN]

    for prefix in _ACCEPTED_PREFIXES:
        if head.startswith(prefix):
            return DocumentType.PASSPORT

    if _is_heic(head):
        raise UnsupportedDocumentError(
            "HEIC/HEIF (iPhone) images aren't supported yet. Export the "
            "photo as JPEG (iOS: Settings → Camera → Formats → Most "
            "Compatible) and resend."
        )

    for prefix, (_mime, msg) in _REJECTED_PREFIXES.items():
        if head.startswith(prefix):
            raise UnsupportedDocumentError(msg)

    raise UnsupportedDocumentError(
        "Unrecognised file format. Send a JPEG, PNG, or TIFF image of "
        f"the passport's photo page. (declared content-type: "
        f"{declared_content_type!r})"
    )
