"""Document type classification.

**Phase 1 honest disclosure:** any valid image or PDF is treated as a
``PASSPORT``. We don't yet have visual cues (logos, format detection) to
reliably tell a passport from an Emirates ID or GCC ID without first
running an extractor. Phase 2 adds a visual classifier (PaddleOCR + a
small image model). Until then, the classifier's job is to:

1. Reject bytes that aren't a recognisable supported format.
2. Tag the input as ``PASSPORT`` so the MRZ pipeline can run.

If the OCR adapter then fails to find an MRZ, we surface
``DOCUMENT_UNREADABLE`` to the consumer, who decides whether to retry
or escalate to manual entry.

**Formats supported in Phase 1:** JPEG, PNG, TIFF, PDF. PDFs are
rasterised (first page only, 200 DPI) in the OCR adapter via PyMuPDF.

**Formats deliberately rejected** (clearer error than letting OCR fail):
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
    b"%PDF-": "application/pdf",
    b"II*\x00": "image/tiff",  # little-endian TIFF
    b"MM\x00*": "image/tiff",  # big-endian TIFF
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
    return None


def _is_heic(head: bytes) -> bool:
    # HEIC files begin with ftyp box: size(4) + 'ftyp'(4) + brand(4) + ...
    return (
        len(head) >= _HEIC_BRAND_END
        and head[4:8] == b"ftyp"
        and head[_HEIC_BRAND_OFFSET:_HEIC_BRAND_END] in _HEIC_BRANDS
    )


def is_pdf(payload: bytes) -> bool:
    """Sniff whether the bytes are a PDF. Used by the OCR adapter to
    decide whether to rasterise before handing off to PassportEye."""
    return payload[:5] == b"%PDF-"


def classify(payload: bytes, declared_content_type: str | None = None) -> DocumentType:
    """Classify the upload. Phase 1 returns ``PASSPORT`` for any valid input.

    Raises ``UnsupportedDocumentError`` for HEIC (until pillow-heif lands)
    and for completely-unknown bytes.
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

    raise UnsupportedDocumentError(
        "Unrecognised file format. Send a JPEG, PNG, TIFF, or PDF of "
        f"the passport's photo page. (declared content-type: "
        f"{declared_content_type!r})"
    )
