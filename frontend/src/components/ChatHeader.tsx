import { Menu, PanelLeftOpen, RefreshCw } from "lucide-react";
import type { BackendStatus } from "../types/rag";

interface ChatHeaderProps {
  title: string;
  sessionId: string;
  backendStatus: BackendStatus;
  isSidebarCollapsed: boolean;
  embedded?: boolean;
  onToggleDesktopSidebar: () => void;
  onOpenMobileSidebar: () => void;
  onRefreshHealth: () => void;
}

export function ChatHeader({
  title,
  sessionId,
  backendStatus,
  isSidebarCollapsed,
  embedded = false,
  onToggleDesktopSidebar,
  onOpenMobileSidebar,
  onRefreshHealth,
}: ChatHeaderProps) {
  const statusLabel =
    backendStatus === "online"
      ? "RAG Connesso"
      : backendStatus === "offline"
        ? "Backend non raggiungibile"
        : "Verifica connessione...";

  return (
    <header className={`chat-header ${embedded ? "chat-header-embedded" : ""}`}>
      <div className="chat-header-left">
        <button
          type="button"
          className="icon-button mobile-only"
          onClick={onOpenMobileSidebar}
          aria-label="Apri menu conversazioni"
        >
          <Menu size={20} />
        </button>

        {isSidebarCollapsed && (
          <button
            type="button"
            className="icon-button desktop-only"
            onClick={onToggleDesktopSidebar}
            aria-label="Espandi barra laterale"
            title="Mostra barra laterale"
          >
            <PanelLeftOpen size={19} />
          </button>
        )}

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
