import { PanelLeft, RefreshCw } from "lucide-react";
import type { BackendStatus } from "../types/rag";

interface ChatHeaderProps {
  title: string;
  sessionId: string;
  backendStatus: BackendStatus;
  embedded?: boolean;
  onToggleSidebar: () => void;
  onRefreshHealth: () => void;
}

export function ChatHeader({
  title,
  sessionId,
  backendStatus,
  embedded = false,
  onToggleSidebar,
  onRefreshHealth,
}: ChatHeaderProps) {
  const statusLabel =
    backendStatus === "online"
      ? "Connesso"
      : backendStatus === "offline"
        ? "Backend non raggiungibile"
        : "Verifica connessione...";

  return (
    <header className={`chat-header ${embedded ? "chat-header-embedded" : ""}`}>
      <div className="chat-header-left">
        <button
          type="button"
          className="icon-button"
          onClick={onToggleSidebar}
          aria-label="Mostra o nascondi elenco conversazioni"
          title="Mostra o nascondi conversazioni"
        >
          <PanelLeft size={19} />
        </button>

        <div className="chat-header-title-group">
          <h2 className="chat-header-title">{title}</h2>
          <span className="session-pill" title="Identificativo sessione corrente">
            Sessione: {sessionId}
          </span>
        </div>
      </div>

      {!embedded && (
        <div className="chat-header-right">
          <button
            type="button"
            className={`status-pill status-pill-${backendStatus}`}
            onClick={onRefreshHealth}
            title="Verifica stato backend RAG"
          >
            <span className="status-dot" aria-hidden="true" />
            <span>{statusLabel}</span>
            <RefreshCw size={13} className={backendStatus === "checking" ? "spin" : ""} aria-hidden="true" />
          </button>
        </div>
      )}
    </header>
  );
}
