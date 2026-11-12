import type {
  KnowledgeDocumentContent,
  KnowledgeDocumentInfo,
  KnowledgeDocumentListItem,
  KnowledgeDocumentsPage,
  KnowledgeIngestSummary,
  KnowledgeUploadResponse,
  RequestAuthContext,
} from "../types/platform";
import { buildAuthHeaders, requestJson } from "./api";

const SUPPORTED_EXTENSIONS = [".csv", ".json", ".md", ".txt"];

function mapDocumentInfoToItem(doc: KnowledgeDocumentInfo): KnowledgeDocumentListItem {
  const normalizedSource = (doc.source || "").replace(/\\/g, "/");
  const parts = normalizedSource.split("/").filter(Boolean);
  const filename = parts[parts.length - 1] || normalizedSource || doc.document_id;
  const dotIdx = filename.lastIndexOf(".");
  const extension = dotIdx >= 0 ? filename.slice(dotIdx).toLowerCase() : "";
  const area = doc.area_name?.trim() || (parts.length > 1 ? parts[0] : "Generale");

  return {
    document_id: doc.document_id,
    filename,
    relative_path: normalizedSource,
    area,
    extension,
    size_bytes: 0,
    status: doc.status,
    chunk_count: doc.chunk_count,
    updated_at: doc.updated_at,
    indexed_at: doc.indexed_at,
  };
}

export async function listKnowledgeDocuments(
  auth: RequestAuthContext,
  params: {
    search?: string;
    area?: string;
    extension?: string;
    page?: number;
    page_size?: number;
  } = {}
): Promise<KnowledgeDocumentsPage> {
  const rawDocs = await requestJson<KnowledgeDocumentInfo[]>("/api/v1/rag/documents?limit=2000", {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });

  const allItems = rawDocs.map(mapDocumentInfoToItem);
  const areasSet = new Set<string>();
  const extSet = new Set<string>();
  let indexedTotal = 0;
  let totalChunks = 0;

  for (const item of allItems) {
    areasSet.add(item.area);
    if (item.extension) extSet.add(item.extension);
    if (item.status === "indexed") indexedTotal += 1;
    totalChunks += item.chunk_count;
  }

  let filtered = allItems;
  if (params.search?.trim()) {
    const needle = params.search.trim().toLowerCase();
    filtered = filtered.filter(
      (it) =>
        it.filename.toLowerCase().includes(needle) ||
        it.relative_path.toLowerCase().includes(needle) ||
        it.area.toLowerCase().includes(needle)
    );
  }
  if (params.area?.trim()) {
    const targetArea = params.area.trim().toLowerCase();
    filtered = filtered.filter((it) => it.area.toLowerCase() === targetArea);
  }
  if (params.extension?.trim()) {
    const rawExt = params.extension.trim().toLowerCase();
    const targetExt = rawExt.startsWith(".") ? rawExt : `.${rawExt}`;
    filtered = filtered.filter((it) => it.extension.toLowerCase() === targetExt);
  }

  const pageSize = params.page_size ?? 25;
  const page = params.page ?? 1;
  const start = (page - 1) * pageSize;

  return {
    total: filtered.length,
    page,
    page_size: pageSize,
    indexed_total: indexedTotal,
    total_chunks: totalChunks,
    areas: Array.from(areasSet).sort(),
    extensions: Array.from(extSet).sort(),
    supported_extensions: SUPPORTED_EXTENSIONS,
    items: filtered.slice(start, start + pageSize),
  };
}

export async function getKnowledgeDocumentContent(
  auth: RequestAuthContext,
  documentId: string
): Promise<KnowledgeDocumentContent> {
  return requestJson<KnowledgeDocumentContent>(
    `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/content`,
    {
      method: "GET",
      headers: buildAuthHeaders(auth),
    }
  );
}

export async function uploadKnowledgeDocuments(
  auth: RequestAuthContext,
  payload: {
    files: File[];
    area?: string;
    overwrite?: boolean;
  }
): Promise<KnowledgeUploadResponse> {
  const formData = new FormData();
  for (const file of payload.files) {
    formData.append("files", file);
  }
  formData.append("area", payload.area?.trim() ?? "");
  formData.append("overwrite", String(Boolean(payload.overwrite)));

  return requestJson<KnowledgeUploadResponse>(
    "/api/v1/knowledge/upload",
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
      body: formData,
    },
    60_000
  );
}

export async function syncKnowledgeBase(auth: RequestAuthContext): Promise<KnowledgeIngestSummary> {
  return requestJson<KnowledgeIngestSummary>(
    "/api/v1/knowledge/ingest",
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
    },
    60_000
  );
}
