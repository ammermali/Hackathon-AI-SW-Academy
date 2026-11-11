/** TypeScript contracts strictly matching the Python FastAPI RAG backend. */

export interface SourceCitation {
  document: string;
  section: string;
  page: number | null;
  chunk_id: string;
  area: string | null;
  relevance_score: number | null;
}

export interface RetrievalInfo {
  documents_found: number;
  relevance_score: number | null;
}

export interface ResponseMetadata {
  cached: boolean;
  processing_time_ms: number;
  needs_escalation: boolean;
  history_id: number | null;
  abstention_reason?: string | null;
}

export interface RAGQueryRequest {
  query: string;
  user_id: string;
  session_id: string;
  top_k?: number;
  user_scope?: "public" | "private";
}

export interface RAGResponse {
  query: string;
  answer: string;
  sources: SourceCitation[];
  retrieval?: RetrievalInfo;
  metadata?: ResponseMetadata;
  cached: boolean;
  processing_time_ms: number;
  needs_escalation: boolean;
  history_id: number | null;
}

export interface HistoryItem {
  id: number;
  user_id: string;
  session_id: string;
  query: string;
  intent: string | null;
  topic: string | null;
  answer: string;
  sources: SourceCitation[];
  cache_hit: boolean;
  processing_time_ms: number;
  needs_escalation: boolean;
  created_at: string;
}

export interface HistoryResponse {
  user_id: string;
  total_returned: number;
  items: HistoryItem[];
  topics_summary: Record<string, number>;
}

export interface DeleteHistoryResponse {
  user_id: string;
  deleted_records: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  corpus_version: string;
}

export type ApiErrorCode =
  | "CONNECTION_UNAVAILABLE"
  | "TIMEOUT"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "INVALID_SESSION"
  | "VALIDATION_ERROR"
  | "EMPTY_RESPONSE"
  | "SERVER_ERROR"
  | "UNKNOWN";

export interface MessageErrorInfo {
  code: ApiErrorCode;
  message: string;
  retryable: boolean;
  originalQuery: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  sources?: SourceCitation[];
  needsEscalation?: boolean;
  abstentionReason?: string | null;
  cached?: boolean;
  processingTimeMs?: number;
  error?: MessageErrorInfo;
}

export interface ConversationSummary {
  sessionId: string;
  title: string;
  updatedAt: string;
  turnCount: number;
  topics: string[];
  messages: ChatMessage[];
}

export type BackendStatus = "checking" | "online" | "offline";
