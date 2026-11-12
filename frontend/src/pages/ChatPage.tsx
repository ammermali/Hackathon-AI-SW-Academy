import { useEffect, useRef, useState } from "react";
import { AlertCircle, Bot, Loader2, X } from "lucide-react";
import { ChatHeader } from "../components/ChatHeader";
import { ChatInput } from "../components/ChatInput";
import { MessageBubble } from "../components/MessageBubble";
import { Sidebar } from "../components/Sidebar";
import { WelcomeEmptyState } from "../components/WelcomeEmptyState";
import { useConversation } from "../hooks/useConversation";

interface ChatPageProps {
  embedded?: boolean;
}

export function ChatPage({ embedded = true }: ChatPageProps) {
  const {
    userId,
    activeSessionId,
    conversations,
    activeMessages,
    backendStatus,
    isLoadingHistory,
    isSending,
    isClearingHistory,
    bannerError,
    clearBannerError,
    refreshHealth,
    changeUserId,
    startNewConversation,
    selectConversation,
    sendMessage,
    retryMessage,
    clearAllHistory,
  } = useConversation();

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeMessages.length, isSending]);

  const activeConv = conversations.find((c) => c.sessionId === activeSessionId);
  const headerTitle = activeConv?.title ?? "Nuova conversazione";

  const handleToggleSidebar = () => {
    if (window.innerWidth <= 900) {
      setIsMobileSidebarOpen((prev) => !prev);
    } else {
      setIsSidebarCollapsed((prev) => !prev);
    }
  };

  return (
    <div className={embedded ? "assistant-workspace" : "app-shell"}>
      <Sidebar
        userId={userId}
        conversations={conversations}
        activeSessionId={activeSessionId}
        isLoadingHistory={isLoadingHistory}
        isClearingHistory={isClearingHistory}
        isCollapsed={isSidebarCollapsed}
        isMobileOpen={isMobileSidebarOpen}
        embedded={embedded}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        onNewConversation={startNewConversation}
        onSelectConversation={selectConversation}
        onChangeUserId={changeUserId}
        onClearAllHistory={clearAllHistory}
      />

      <main className="chat-main">
        <ChatHeader
          title={headerTitle}
          sessionId={activeSessionId}
          backendStatus={backendStatus}
          embedded={embedded}
          onToggleSidebar={handleToggleSidebar}
          onRefreshHealth={() => void refreshHealth()}
        />

        {bannerError && (
          <div className="global-error-banner" role="alert">
            <div className="global-error-text">
              <AlertCircle size={16} aria-hidden="true" />
              <span>{bannerError}</span>
            </div>
            <button
              type="button"
              className="icon-button"
              onClick={clearBannerError}
              aria-label="Chiudi avviso"
            >
              <X size={16} />
            </button>
          </div>
        )}

        <div className="chat-scroll-area">
          <div className="chat-container">
            {activeMessages.length === 0 ? (
              <WelcomeEmptyState onSelectPrompt={(p) => void sendMessage(p)} disabled={isSending} />
            ) : (
              <div className="messages-thread" aria-live="polite">
                {activeMessages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    onRetry={(id) => void retryMessage(id)}
                    isBusy={isSending}
                  />
                ))}

                {isSending && (
                  <div className="message-row message-row-assistant" role="status" aria-label="Elaborazione risposta">
                    <div className="avatar avatar-assistant" aria-hidden="true">
                      <Bot size={17} />
                    </div>
                    <div className="message-bubble message-bubble-assistant thinking-bubble">
                      <Loader2 size={16} className="spin" aria-hidden="true" />
                      <span>Ricerca nei documenti e generazione risposta con Qwen...</span>
                    </div>
                  </div>
                )}
              </div>
            )}
            <div ref={threadEndRef} />
          </div>
        </div>

        <footer className="chat-footer">
          <div className="chat-container">
            <ChatInput onSend={sendMessage} isSending={isSending} />
          </div>
        </footer>
      </main>
    </div>
  );
}
