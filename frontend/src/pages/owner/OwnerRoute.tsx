import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export function OwnerRoute({ children }: { children: ReactNode }) {
  const { isOwner, user, demoModeEnabled } = useAuth();

  if (!isOwner) {
    return (
      <div className="page-container">
        <section className="empty-card owner-guard-card" role="alert">
          <Lock size={28} aria-hidden="true" />
          <h1>Accesso riservato all&apos;Area Learning Manager</h1>
          <p>
            Il profilo attivo (<strong>{user.displayName}</strong>, ruolo{" "}
            <code>{user.role === "owner" || user.role === "learning_manager" ? "learning manager" : user.role}</code>)
            non dispone dei permessi Learning Manager necessari per consultare analisi apprendimento e governance.
          </p>
          {demoModeEnabled && (
            <p className="muted-meta">
              Se stai testando la piattaforma in Demo Mode, seleziona un profilo Learning Manager (es.{" "}
              <code>owner_demo</code>) dal selettore utente nell&apos;header in alto.
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
