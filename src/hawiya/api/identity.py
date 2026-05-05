"""``POST /v1/identity/resolve`` — extract + match in a single call.

Pipeline (synchronous): classify → OCR → parse → match → optional create.
On any extraction failure, the same error envelope as ``/v1/documents/extract``
is returned (extraction is the first step here too).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse

from hawiya.api.dependencies import get_identity_service
from hawiya.api.errors import error_response
from hawiya.extractors.document_classifier import UnsupportedDocumentError
from hawiya.extractors.mrz import MRZFormatError
from hawiya.extractors.ocr import NoMRZFoundError, OCRUnavailableError
from hawiya.services.identity_service import IdentityService, ResolveResult
from hawiya.tenancy.context import require_tenant_id

router = APIRouter(prefix="/v1/identity", tags=["identity"])

MAX_PAYLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/resolve",
    response_model=ResolveResult,
    responses={
        400: {"description": "Empty upload"},
        413: {"description": "Payload too large"},
        415: {"description": "Unsupported document type"},
        422: {"description": "Document unreadable"},
        503: {"description": "OCR backend unavailable"},
    },
)
async def resolve_identity(
    file: UploadFile = File(..., description="Passport image (JPEG/PNG/TIFF) or PDF"),
    consumer_request_id: str | None = Form(default=None),
    create_if_missing: bool = Form(default=True),
    service: IdentityService = Depends(get_identity_service),
) -> ResolveResult | JSONResponse:
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
        return await service.resolve(
            tenant_id,
            payload,
            file.content_type or "application/octet-stream",
            consumer_request_id=consumer_request_id,
            create_if_missing=create_if_missing,
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
