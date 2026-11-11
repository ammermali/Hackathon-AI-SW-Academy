/** Runtime frontend configuration loaded strictly from Vite public env vars. */

const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";
const rawDefaultUser = (import.meta.env.VITE_DEFAULT_USER_ID as string | undefined) ?? "operatore_01";
const rawTimeout = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 45000);

export const APP_CONFIG = {
  apiBaseUrl: rawBaseUrl.trim().replace(/\/+$/, "") || "http://localhost:8000",
  defaultUserId: rawDefaultUser.trim() || "operatore_01",
  requestTimeoutMs: Number.isFinite(rawTimeout) && rawTimeout >= 1000 ? rawTimeout : 45000,
} as const;
