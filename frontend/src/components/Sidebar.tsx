import { useState, type FormEvent } from "react";
import {
  MessageSquare,
  Plus,
  Trash2,
  UserCheck,
} from "lucide-react";
import type { ConversationSummary } from "../types/rag";

interface SidebarProps {
  userId: string;
  conversations: ConversationSummary[];
  activeSessionId: string;
  isLoadingHistory: boolean;
  isClearingHistory: boolean;
  isCollapsed: boolean;
  isMobileOpen: boolean;
  embedded?: boolean;
  onCloseMobile: () => void;
  onNewConversation: () => void;
  onSelectConversation: (sessionId: string) => void;
  onChangeUserId: (nextUserId: string) => void;
  onClearAllHistory: () => Promise<void>;
}

function formatShortDate(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

export function Sidebar({
  userId,
  conversations,
  activeSessionId,
  isLoadingHistory,
  isClearingHistory,
  isCollapsed,
  isMobileOpen,
  embedded = false,
  onCloseMobile,
  onNewConversation,
  onSelectConversation,
  onChangeUserId,
  onClearAllHistory,
}: SidebarProps) {
  const [confirmClear, setConfirmClear] = useState(false);
  const [editingUser, setEditingUser] = useState(false);
  const [draftUserId, setDraftUserId] = useState(userId);

  const handleUserSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (draftUserId.trim()) {
      onChangeUserId(draftUserId.trim());
    }
    setEditingUser(false);
  };

  const handleConfirmDeleteAll = async () => {
    await onClearAllHistory();
    setConfirmClear(false);
  };

  return (
    <>
      {isMobileOpen && (
        <div
          className="sidebar-backdrop mobile-only"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`sidebar ${isCollapsed ? "sidebar-collapsed" : ""} ${isMobileOpen ? "sidebar-mobile-open" : ""}`}
        aria-label="Navigazione conversazioni"
      >
        <div className="sidebar-top">
          {embedded ? (
            <div className="brand-block">
              <div>
                <div className="brand-name">Conversazioni</div>
                <div className="brand-sub">Storico Operator Copilot</div>
              </div>
            </div>
          ) : (
            <div className="brand-block">
              <div className="brand-logo" aria-hidden="true">
                <img src="/brand-logo.png" alt="" className="brand-logo-img" />
              </div>
              <div>
                <div className="brand-name">AI Software Academy</div>
                <div className="brand-sub">Assistente RAG</div>
              </div>
            </div>
          )}
        </div>

        <div className="sidebar-actions">
          <button
            type="button"
            className="new-chat-button"
            onClick={() => {
              onNewConversation();
              onCloseMobile();
            }}
          >
            <Plus size={16} aria-hidden="true" />
            <span>Nuova conversazione</span>
          </button>
        </div>

        <div className="sidebar-section-label">
          <span>Conversazioni precedenti</span>
          {isLoadingHistory && <span className="sidebar-loading-tag">Aggiornamento...</span>}
        </div>

        <nav className="conversation-list" aria-label="Elenco conversazioni salvate">
          {conversations.length === 0 ? (
            <p className="empty-history-hint">
              {isLoadingHistory
                ? "Caricamento storico dal backend..."
                : "Nessuna conversazione salvata per questo operatore."}
            </p>
          ) : (
            <ul>
              {conversations.map((conv) => {
                const isActive = conv.sessionId === activeSessionId;
                return (
                  <li key={conv.sessionId}>
                    <button
                      type="button"
                      className={`conversation-item ${isActive ? "conversation-item-active" : ""}`}
                      onClick={() => {
                        onSelectConversation(conv.sessionId);
                        onCloseMobile();
                      }}
                    >
                      <MessageSquare size={15} className="conversation-icon" aria-hidden="true" />
                      <div className="conversation-item-text">
                        <span className="conversation-title">{conv.title}</span>
                        <span className="conversation-meta">
                          {conv.turnCount} {conv.turnCount === 1 ? "domanda" : "domande"} •{" "}
                          {formatShortDate(conv.updatedAt)}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <div className="sidebar-footer">
          {!embedded && (
            <div className="user-profile-box">
              {editingUser ? (
                <form className="user-edit-form" onSubmit={handleUserSubmit}>
                  <label htmlFor="operator-id-input" className="sr-only">
                    Identificativo operatore
                  </label>
                  <input
                    id="operator-id-input"
                    type="text"
                    value={draftUserId}
                    onChange={(e) => setDraftUserId(e.target.value)}
                    maxLength={128}
                    placeholder="ID operatore"
                    autoFocus
                  />
                  <button type="submit" className="mini-btn mini-btn-primary">
                    Salva
                  </button>
                  <button
                    type="button"
                    className="mini-btn"
                    onClick={() => {
                      setDraftUserId(userId);
                      setEditingUser(false);
                    }}
                  >
                    Annulla
                  </button>
                </form>
              ) : (
                <div className="user-display-row">
                  <span className="user-badge" title="Identificativo operatore associato allo storico">
                    <UserCheck size={14} aria-hidden="true" />
                    <span>{userId}</span>
                  </span>
                  <button
                    type="button"
                    className="text-link-button"
                    onClick={() => {
                      setDraftUserId(userId);
                      setEditingUser(true);
                    }}
                  >
                    Cambia
                  </button>
                </div>
              )}
            </div>
          )}

          {conversations.length > 0 && (
            <div className="clear-history-box">
              {confirmClear ? (
                <div className="confirm-clear-panel" role="alertdialog" aria-label="Conferma cancellazione storico">
                  <p>Eliminare l&apos;intero storico di {userId} sul server?</p>
                  <div className="confirm-clear-actions">
                    <button
                      type="button"
                      className="mini-btn mini-btn-danger"
                      disabled={isClearingHistory}
                      onClick={() => void handleConfirmDeleteAll()}
                    >
                      {isClearingHistory ? "Eliminazione..." : "Conferma"}
                    </button>
                    <button
                      type="button"
                      className="mini-btn"
                      disabled={isClearingHistory}
                      onClick={() => setConfirmClear(false)}
                    >
                      Annulla
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="clear-history-button"
                  onClick={() => setConfirmClear(true)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                  <span>Cancella tutta la cronologia</span>
                </button>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
