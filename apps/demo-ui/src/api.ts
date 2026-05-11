// Tiny client for the Hawiya AI API. Reads its config from runtime
// environment so the same build can target dev, staging, etc.

const BASE_URL =
  (import.meta as ImportMeta & { env: Record<string, string> }).env
    .VITE_HAWIYA_BASE_URL ?? "http://localhost:8010";
const TENANT_ID = (import.meta as ImportMeta & {
  env: Record<string, string>;
}).env.VITE_HAWIYA_TENANT_ID ?? "";
const BEARER = (import.meta as ImportMeta & {
  env: Record<string, string>;
}).env.VITE_HAWIYA_BEARER ?? "dev";

// /v1/identity/resolve — registry mode.
export type ResolveAction =
  | "new_record"
  | "auto_matched"
  | "suggested_match"
  | "manual_review"
  | "no_match_no_create";

export interface ResolveResult {
  extraction_id: string;
  action: ResolveAction;
  person_uuid: string | null;
  confidence: number;
  method: string;
  fields: Record<string, string | null>;
}

// /v1/documents/extract — WizSM mode (extract-only).
export type ChecksumStatus = "all_pass" | "partial" | "all_fail" | "n/a";

export interface ExtractResult {
  extraction_id: string;
  document_type: string;
  fields: Record<string, string | null>;
  confidence_per_field: Record<string, number>;
  checksum_status: ChecksumStatus;
  processing_path: string;
  processing_time_ms: number;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  trace_id?: string;
}

export class ApiCallError extends Error {
  constructor(public status: number, public body: { error?: ApiError }) {
    super(body.error?.message ?? `HTTP ${status}`);
  }
}

export const config = {
  baseUrl: BASE_URL,
  tenantId: TENANT_ID,
  bearer: BEARER,
};

function authHeaders(): HeadersInit {
  return {
    Authorization: `Bearer ${BEARER}`,
    "X-Tenant-ID": TENANT_ID,
  };
}

async function postFile<T>(
  path: string,
  fileBytes: Blob,
  filename: string
): Promise<T> {
  if (!TENANT_ID) {
    throw new ApiCallError(0, {
      error: {
        code: "CONFIG_MISSING",
        message:
          "VITE_HAWIYA_TENANT_ID is not set. Edit apps/demo-ui/.env.local.",
      },
    });
  }
  const form = new FormData();
  form.append("file", fileBytes, filename);

  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
  } catch (err) {
    throw new ApiCallError(0, {
      error: {
        code: "NETWORK_ERROR",
        message: `Could not reach ${BASE_URL}: ${(err as Error).message}`,
      },
    });
  }

  let body: { error?: ApiError } & Partial<T>;
  try {
    body = (await resp.json()) as never;
  } catch {
    throw new ApiCallError(resp.status, {
      error: {
        code: "BAD_RESPONSE",
        message: `Non-JSON response (${resp.status})`,
      },
    });
  }
  if (!resp.ok) {
    throw new ApiCallError(resp.status, body);
  }
  return body as T;
}

export function resolveIdentity(
  fileBytes: Blob,
  filename = "passport.jpg"
): Promise<ResolveResult> {
  return postFile<ResolveResult>(
    "/v1/identity/resolve",
    fileBytes,
    filename
  );
}

export function extractDocument(
  fileBytes: Blob,
  filename = "passport.jpg"
): Promise<ExtractResult> {
  return postFile<ExtractResult>(
    "/v1/documents/extract",
    fileBytes,
    filename
  );
}
