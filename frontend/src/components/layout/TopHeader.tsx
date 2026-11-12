import { Building2, Cpu, Menu, RefreshCw, ShieldCheck } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { formatRoleLabel } from "../../types/platform";
import { DemoUserSwitcher } from "./DemoUserSwitcher";

interface TopHeaderProps {
  onToggleSidebar: () => void;
}

export function TopHeader({ onToggleSidebar }: TopHeaderProps) {
  const { user, backendStatus, refreshHealth } = useAuth();

  const statusLabel =
    backendStatus === "online"
      ? "Connesso"
      : backendStatus === "offline"
        ? "Offline"
        : "Verifica...";

  return (
    <header className="top-header">
      <div className="top-header-left">
        <button
          type="button"
          className="icon-button"
          onClick={onToggleSidebar}
          aria-label="Apri o chiudi menu navigazione"
          title="Mostra o nascondi menu"
        >
          <Menu size={20} />
        </button>

        <div className="user-identity-strip">
          <div className="identity-avatar" aria-hidden="true">
            {user.displayName.slice(0, 2).toUpperCase()}
          </div>
          <div className="identity-meta">
            <div className="identity-name-row">
              <strong className="identity-name">{user.displayName}</strong>
              <span className={`role-chip role-chip-${user.role}`}>
                <ShieldCheck size={11} aria-hidden="true" />
                {formatRoleLabel(user.role)}
              </span>
            </div>
            <div className="identity-sub-row">
              <span className="identity-sub-item">
                <Building2 size={12} aria-hidden="true" />
                {user.amministrazione}
              </span>
              {user.softwaresUsed.length > 0 && (
                <span className="identity-sub-item identity-software-list">
                  <Cpu size={12} aria-hidden="true" />
                  {user.softwaresUsed.slice(0, 2).join(", ")}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="top-header-right">
        <DemoUserSwitcher />

        <button
          type="button"
          className={`status-pill status-pill-${backendStatus}`}
          onClick={() => void refreshHealth()}
          title="Verifica stato backend RAG"
        >
          <span className="status-dot" aria-hidden="true" />
          <span className="status-text-responsive">{statusLabel}</span>
          <RefreshCw size={13} className={backendStatus === "checking" ? "spin" : ""} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
