import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Loader2, SendHorizontal } from "lucide-react";

interface ChatInputProps {
  onSend: (query: string) => Promise<void> | void;
  isSending: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, isSending, disabled = false }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const submitQuery = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setValidationError("Inserisci una domanda prima di inviare.");
      return;
    }
    if (trimmed.length < 2) {
      setValidationError("La domanda deve contenere almeno 2 caratteri.");
      return;
    }
    if (isSending || disabled) {
      return;
    }

    setValidationError(null);
    setValue("");
    await onSend(trimmed);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submitQuery();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submitQuery();
    }
  };

  const canSend = value.trim().length >= 2 && !isSending && !disabled;

  return (
    <div className="composer-wrapper">
      {validationError && (
        <p className="composer-validation-error" role="alert">
          {validationError}
        </p>
      )}

      <form className="composer-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="rag-chat-input" className="sr-only">
          Scrivi la tua domanda per AI Software Academy
        </label>
        <textarea
          ref={textareaRef}
          id="rag-chat-input"
          className="composer-textarea"
          rows={1}
          maxLength={2000}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (validationError) setValidationError(null);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Fai una domanda sui manuali e sulle procedure..."
          disabled={disabled}
          aria-invalid={Boolean(validationError)}
        />

        <button
          type="submit"
          className="send-button"
          disabled={!canSend}
          aria-label={isSending ? "Generazione in corso" : "Invia domanda"}
          title={isSending ? "Generazione in corso..." : "Invia domanda (Invio)"}
        >
          {isSending ? <Loader2 size={18} className="spin" aria-hidden="true" /> : <SendHorizontal size={18} aria-hidden="true" />}
          <span className="send-button-label">{isSending ? "Invio..." : "Invia"}</span>
        </button>
      </form>

      <div className="composer-hint">
        <span>Premi Invio per inviare • Maiusc + Invio per andare a capo</span>
        <span>{value.length}/2000</span>
      </div>
    </div>
  );
}
