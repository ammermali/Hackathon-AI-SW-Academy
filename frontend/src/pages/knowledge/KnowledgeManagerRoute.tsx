import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export function KnowledgeManagerRoute({ children }: { children: ReactNode }) {
  const { isKnowledgeManager, user, demoModeEnabled } = useAuth();

  if (!isKnowledgeManager) {
    return (
      <div className="page-container">
        <section className="empty-card owner-guard-card" role="alert">
          <Lock size={28} aria-hidden="true" />
          <h1>Accesso riservato al Knowledge Manager</h1>
          <p>
            Il profilo attivo (<strong>{user.displayName}</strong>, ruolo <code>{user.role}</code>)
            non dispone dei permessi per gestire e caricare documenti nella Knowledge Base.
          </p>
          {demoModeEnabled && (
            <p className="muted-meta">
              Se stai testando in Demo Mode, seleziona un profilo Knowledge Manager (es.{" "}
              <code>km_paolo</code>) dal selettore utente nell&apos;header in alto.
            </p>
          )}
          <div className="hero-actions">
            <Link to="/" className="btn btn-primary">
              Torna alla Home
            </Link>
          </div>
        </section>
      </div>
    );
  }

  return <>{children}</>;
}
