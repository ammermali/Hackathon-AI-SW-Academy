import { buildAuthHeaders, requestJson } from "./api";
import type { DemoStatusResponse, DemoSwitchResponse, DemoUserItem } from "../types/platform";

export async function getDemoStatus(): Promise<DemoStatusResponse> {
  return requestJson<DemoStatusResponse>("/api/v1/demo/status", { method: "GET" }, 6000);
}

export async function listDemoUsers(tenantId = "default"): Promise<DemoUserItem[]> {
  return requestJson<DemoUserItem[]>("/api/v1/demo/users", {
    method: "GET",
    headers: buildAuthHeaders({ tenantId, userId: "anonymous", role: "operatore", demoToken: null }),
  });
}

export async function switchDemoUser(tenantId: string, userId: string): Promise<DemoSwitchResponse> {
  return requestJson<DemoSwitchResponse>("/api/v1/demo/switch-user", {
    method: "POST",
    headers: { "X-Tenant-ID": tenantId || "default" },
    body: JSON.stringify({ user_id: userId }),
  });
}
