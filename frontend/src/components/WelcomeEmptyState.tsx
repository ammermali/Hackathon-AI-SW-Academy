import { Sparkles, ArrowRight } from "lucide-react";

interface WelcomeEmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
  disabled?: boolean;
}

const STARTER_PROMPTS = [
  "Come si apre correttamente una richiesta di assistenza clienti?",
  "Come si rimuove un verbale da un ruolo?",
  "Qual è la procedura per i pagamenti PagoPA su SIOPE+?",
];

export function WelcomeEmptyState({ onSelectPrompt, disabled = false }: WelcomeEmptyStateProps) {
  return (
    <div className="welcome-container">
      <div className="welcome-badge">
        <Sparkles size={18} aria-hidden="true" />
        <span>AI Software Academy</span>
      </div>

      <h1 className="welcome-title">Come posso aiutarti oggi?</h1>
      <p className="welcome-subtitle">
        Fai una domanda sulla documentazione applicativa aziendale. Le risposte sono generate da Qwen tramite il
        motore RAG e accompagnate dalle fonti documentali utilizzate.
      </p>

      <div className="starter-grid" aria-label="Domande suggerite">
        {STARTER_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="starter-card"
            disabled={disabled}
            onClick={() => onSelectPrompt(prompt)}
          >
            <span>{prompt}</span>
            <ArrowRight size={15} className="starter-arrow" aria-hidden="true" />
          </button>
        ))}
      </div>
    </div>
  );
}
