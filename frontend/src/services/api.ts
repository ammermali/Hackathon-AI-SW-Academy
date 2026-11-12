import { APP_CONFIG } from "../config/env";
import type { RequestAuthContext } from "../types/platform";
import type {
  ApiErrorCode,
  DeleteHistoryResponse,
  HealthResponse,
  HistoryResponse,
  RAGQueryRequest,
  RAGResponse,
} from "../types/rag";

export class ApiClientError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly retryable: boolean;

  constructor(code: ApiErrorCode, message: string, options?: { status?: number; retryable?: boolean }) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.status = options?.status;
    this.retryable = options?.retryable ?? true;
  }
}

function extractFastApiDetail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as Record<string, unknown>).msg);
        }
        return null;
      })
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return null;
}

function mapHttpError(status: number, body: unknown): ApiClientError {
  const detail = extractFastApiDetail(body);

  if (status === 401) {
    return new ApiClientError("UNAUTHORIZED", detail ?? "Autenticazione richiesta o sessione non valida.", {
      status,
      retryable: false,
    });
  }
  if (status === 403) {
    return new ApiClientError("FORBIDDEN", detail ?? "Non disponi dei permessi necessari per questa operazione.", {
      status,
      retryable: false,
    });
  }
  if (status === 404) {
    return new ApiClientError("INVALID_SESSION", detail ?? "Risorsa o sessione non trovata sul server.", {
      status,
      retryable: false,
    });
  }
  if (status === 400 || status === 422) {
    return new ApiClientError("VALIDATION_ERROR", detail ?? "Richiesta non valida. Verifica il testo inserito.", {
      status,
      retryable: false,
    });
  }
  if (status >= 500) {
    return new ApiClientError("SERVER_ERROR", detail ?? "Errore interno del server RAG durante l'elaborazione.", {
      status,
      retryable: true,
    });
  }
  return new ApiClientError("UNKNOWN", detail ?? `Errore imprevisto (HTTP ${status}).`, {
    status,
    retryable: true,
  });
}

export function buildAuthHeaders(auth?: RequestAuthContext | null): Record<string, string> {
  if (!auth) return {};
  const headers: Record<string, string> = {
    "X-Tenant-ID": auth.tenantId || "default",
  };
  if (auth.demoToken) {
    headers["X-Demo-Token"] = auth.demoToken;
  } else {
    headers["X-User-ID"] = auth.userId || "anonymous";
    headers["X-User-Role"] = auth.role || "operatore";
  }
  return headers;
}

export async function requestJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = APP_CONFIG.requestTimeoutMs
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${APP_CONFIG.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });

    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
    }

    if (!response.ok) {
      throw mapHttpError(response.status, parsed);
    }

    if (parsed === null) {
      throw new ApiClientError("EMPTY_RESPONSE", "Il backend ha restituito una risposta vuota o non valida.", {
        status: response.status,
        retryable: true,
      });
    }

    return parsed as T;
  } catch (err) {
    if (err instanceof ApiClientError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiClientError(
        "TIMEOUT",
        "La generazione della risposta ha superato il tempo limite. Riprova tra qualche istante.",
        { retryable: true }
      );
    }
    if (err instanceof TypeError) {
      throw new ApiClientError(
        "CONNECTION_UNAVAILABLE",
        `Connessione al backend non disponibile (${APP_CONFIG.apiBaseUrl}). Verifica che il servizio FastAPI sia attivo.`,
        { retryable: true }
      );
    }
    throw new ApiClientError("UNKNOWN", "Errore di rete imprevisto durante la comunicazione con il backend.", {
      retryable: true,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function checkHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health", { method: "GET" }, 6000);
}

export async function sendRagQuery(
  payload: RAGQueryRequest,
  auth?: RequestAuthContext | null
): Promise<RAGResponse> {
  const data = await requestJson<RAGResponse>("/api/v1/rag/query", {
    method: "POST",
    headers: buildAuthHeaders(auth),
    body: JSON.stringify(payload),
  });

  if (!data.answer || !data.answer.trim()) {
    throw new ApiClientError("EMPTY_RESPONSE", "Il modello non ha restituito alcun contenuto nella risposta.", {
      retryable: true,
    });
  }

  return data;
}

export async function fetchUserHistory(
  userId: string,
  limit = 200,
  auth?: RequestAuthContext | null
): Promise<HistoryResponse> {
  const encodedUser = encodeURIComponent(userId);
  return requestJson<HistoryResponse>(`/api/v1/rag/history/${encodedUser}?limit=${limit}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function deleteUserHistory(
  userId: string,
  auth?: RequestAuthContext | null
): Promise<DeleteHistoryResponse> {
  const encodedUser = encodeURIComponent(userId);
  return requestJson<DeleteHistoryResponse>(`/api/v1/rag/history/${encodedUser}`, {
    method: "DELETE",
    headers: buildAuthHeaders(auth),
  });
}
