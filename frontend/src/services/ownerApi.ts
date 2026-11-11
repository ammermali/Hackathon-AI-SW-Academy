import { buildAuthHeaders, requestJson } from "./api";
import type {
  OwnerCustomQuizAnalytics,
  OwnerInsightsResponse,
  OwnerOverview,
  OwnerTopicDrilldown,
  OwnerTopicReviewItem,
  OwnerUserDetail,
  OwnerUsersPage,
  RequestAuthContext,
} from "../types/platform";

function buildQueryString(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && String(v).trim() !== "") {
      sp.set(k, String(v));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function getOwnerOverview(
  auth: RequestAuthContext,
  params: { software?: string; module_name?: string; amministrazione?: string; refresh?: boolean } = {}
): Promise<OwnerOverview> {
  const qs = buildQueryString(params);
  return requestJson<OwnerOverview>(`/api/v1/owner/overview${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function listOwnerUsers(
  auth: RequestAuthContext,
  params: {
    search?: string;
    amministrazione?: string;
    software?: string;
    learning_status?: string;
    sort_by?: string;
    sort_dir?: "asc" | "desc";
    page?: number;
    page_size?: number;
  } = {}
): Promise<OwnerUsersPage> {
  const qs = buildQueryString(params);
  return requestJson<OwnerUsersPage>(`/api/v1/owner/users${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getOwnerUserDetail(auth: RequestAuthContext, userId: string): Promise<OwnerUserDetail> {
  return requestJson<OwnerUserDetail>(`/api/v1/owner/users/${encodeURIComponent(userId)}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function listOwnerTopicsToReview(
  auth: RequestAuthContext,
  params: { software?: string; amministrazione?: string; criticality?: string } = {}
): Promise<OwnerTopicReviewItem[]> {
  const qs = buildQueryString(params);
  return requestJson<OwnerTopicReviewItem[]>(`/api/v1/owner/topics-to-review${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getTopicUsersDrilldown(
  auth: RequestAuthContext,
  topic: string,
  amministrazione?: string
): Promise<OwnerTopicDrilldown> {
  const qs = buildQueryString({ amministrazione });
  return requestJson<OwnerTopicDrilldown>(`/api/v1/owner/topics-to-review/${encodeURIComponent(topic)}/users${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getOwnerCustomQuizAnalytics(
  auth: RequestAuthContext,
  params: { software?: string; amministrazione?: string } = {}
): Promise<OwnerCustomQuizAnalytics> {
  const qs = buildQueryString(params);
  return requestJson<OwnerCustomQuizAnalytics>(`/api/v1/owner/customquiz-analytics${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getOwnerInsights(
  auth: RequestAuthContext,
  params: { software?: string; amministrazione?: string; use_llm_synthesis?: boolean } = {}
): Promise<OwnerInsightsResponse> {
  const qs = buildQueryString(params);
  return requestJson<OwnerInsightsResponse>(`/api/v1/owner/insights${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}
