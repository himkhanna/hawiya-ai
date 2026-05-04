"""``POST /v1/documents/extract`` — synchronous document extraction.

Accepts a single image or PDF, returns an ``ExtractionResult`` envelope
with parsed fields, per-field confidence, and the checksum status. Phase 1
walks only the deterministic MRZ path; visual/LLM branches arrive in
Phase 2.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse

from hawiya.api.dependencies import get_extraction_service
from hawiya.api.errors import error_response
from hawiya.extractors.document_classifier import UnsupportedDocumentError
from hawiya.extractors.mrz import MRZFormatError
from hawiya.extractors.ocr import NoMRZFoundError, OCRUnavailableError
from hawiya.extractors.types import ExtractionResult
from hawiya.services.extraction_service import ExtractionService
from hawiya.tenancy.context import require_tenant_id

router = APIRouter(prefix="/v1/documents", tags=["documents"])

# 10 MB ceiling on a single upload — enough for high-DPI passport scans
# while keeping a memory bound on the API process.
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/extract",
    response_model=ExtractionResult,
    responses={
        400: {"description": "Empty upload"},
        413: {"description": "Payload too large"},
        415: {"description": "Unsupported document type"},
        422: {"description": "Document unreadable"},
        503: {"description": "OCR backend unavailable"},
    },
)
async def extract_document(
    file: UploadFile = File(..., description="Passport image (JPEG/PNG/TIFF) or PDF"),
    consumer_request_id: str | None = Form(default=None),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResult | JSONResponse:
    tenant_id = require_tenant_id()

    payload = await file.read()
    if not payload:
        return error_response(
            code="EMPTY_UPLOAD",
            message="The uploaded file was empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if len(payload) > MAX_PAYLOAD_BYTES:
        return error_response(
            code="PAYLOAD_TOO_LARGE",
            message=f"Maximum upload size is {MAX_PAYLOAD_BYTES // (1024 * 1024)} MB.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"size_bytes": len(payload)},
        )

    try:
        return await service.extract(
            tenant_id,
            payload,
            file.content_type or "application/octet-stream",
            consumer_request_id=consumer_request_id,
        )
    except UnsupportedDocumentError as e:
        return error_response(
            code="UNSUPPORTED_DOCUMENT",
            message=str(e),
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    except (NoMRZFoundError, MRZFormatError) as e:
        return error_response(
            code="DOCUMENT_UNREADABLE",
            message=str(e),
            status_code=422,
        )
    except OCRUnavailableError as e:
        return error_response(
            code="OCR_UNAVAILABLE",
            message=str(e),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
