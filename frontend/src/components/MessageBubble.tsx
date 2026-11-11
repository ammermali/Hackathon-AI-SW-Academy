import { useState } from "react";
import { AlertTriangle, Bot, Check, Copy, RotateCcw, User } from "lucide-react";
import type { ChatMessage } from "../types/rag";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { SourcesAccordion } from "./SourcesAccordion";

interface MessageBubbleProps {
  message: ChatMessage;
  onRetry?: (messageId: string) => void;
  isBusy?: boolean;
}

function formatTime(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message, onRetry, isBusy = false }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!message.content) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard API might be unavailable in restricted contexts
    }
  };

  if (message.role === "user") {
    return (
      <article className="message-row message-row-user" aria-label="Messaggio utente">
        <div className="message-bubble message-bubble-user">
          <div className="message-meta message-meta-user">
            <span className="message-author">Tu</span>
            {formatTime(message.createdAt) && <span className="message-time">{formatTime(message.createdAt)}</span>}
          </div>
          <p className="user-message-text">{message.content}</p>
        </div>
        <div className="avatar avatar-user" aria-hidden="true">
          <User size={16} />
        </div>
      </article>
    );
  }

  return (
    <article className="message-row message-row-assistant" aria-label="Risposta AI Software Academy">
      <div className="avatar avatar-assistant" aria-hidden="true">
        <Bot size={17} />
      </div>

      <div className="message-bubble message-bubble-assistant">
        <div className="message-meta message-meta-assistant">
          <div className="message-meta-left">
            <span className="message-author">AI Software Academy</span>
            {formatTime(message.createdAt) && <span className="message-time">{formatTime(message.createdAt)}</span>}
          </div>

          {!message.error && message.content && (
            <button
              type="button"
              className="copy-button"
              onClick={handleCopy}
              aria-label="Copia risposta"
              title="Copia risposta negli appunti"
            >
              {copied ? (
                <>
                  <Check size={14} aria-hidden="true" />
                  <span>Copiato</span>
                </>
              ) : (
                <>
                  <Copy size={14} aria-hidden="true" />
                  <span>Copia</span>
                </>
              )}
            </button>
          )}
        </div>

        {message.error ? (
          <div className="message-error-box" role="alert">
            <div className="message-error-content">
              <AlertTriangle size={17} aria-hidden="true" />
              <div>
                <strong>Impossibile completare la richiesta</strong>
                <p>{message.error.message}</p>
              </div>
            </div>
            {message.error.retryable && onRetry && (
              <button
                type="button"
                className="retry-button"
                disabled={isBusy}
                onClick={() => onRetry(message.id)}
              >
                <RotateCcw size={14} aria-hidden="true" />
                <span>Riprova</span>
              </button>
            )}
          </div>
        ) : (
          <>
            {message.needsEscalation && (
              <div className="escalation-notice" role="status">
                <AlertTriangle size={15} aria-hidden="true" />
                <span>
                  Evidenza documentale parziale o assente: potrebbe essere utile verificare con il supporto applicativo.
                </span>
              </div>
            )}

            <div className="assistant-answer-content">
              <MarkdownRenderer content={message.content} />
            </div>

            {message.sources && message.sources.length > 0 && <SourcesAccordion sources={message.sources} />}
          </>
        )}
      </div>
    </article>
  );
}
