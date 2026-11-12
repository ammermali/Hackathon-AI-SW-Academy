import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { formatRoleLabel } from "../../types/platform";

export function DemoUserSwitcher() {
  const { user, demoModeEnabled, demoUsers, isSwitchingUser, switchUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return demoUsers;
    return demoUsers.filter(
      (u) =>
        u.display_name.toLowerCase().includes(q) ||
        u.user_id.toLowerCase().includes(q) ||
        u.amministrazione.toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q)
    );
  }, [demoUsers, search]);

  if (!demoModeEnabled) {
    return null;
  }

  return (
    <div className="demo-switcher" ref={containerRef}>
      <button
        type="button"
        className="demo-switcher-trigger"
        onClick={() => setOpen((prev) => !prev)}
        disabled={isSwitchingUser}
        aria-expanded={open}
        aria-haspopup="listbox"
        title="Modalità Demo: cambia utente tra quelli presenti nel sistema"
      >
        <span className="demo-tag">DEMO</span>
        <span className="demo-trigger-name">{isSwitchingUser ? "Cambio..." : user.displayName}</span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>

      {open && (
        <div className="demo-dropdown" role="dialog" aria-label="Selettore utente Demo">
          <div className="demo-dropdown-banner">
            <strong>Modalità Demo Locale</strong>
            <span>Switch controllato dal backend (disabilitato in produzione)</span>
          </div>

          <div className="demo-search-box">
            <Search size={14} aria-hidden="true" />
            <input
              type="text"
              placeholder="Cerca utente, ente o ruolo..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
          </div>

          <ul className="demo-user-list" role="listbox" aria-label="Utenti disponibili">
            {filtered.length === 0 ? (
              <li className="demo-empty">Nessun utente trovato nel tenant corrente.</li>
            ) : (
              filtered.map((item) => {
                const isSelected = item.user_id === user.userId;
                return (
                  <li key={item.user_id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`demo-user-option ${isSelected ? "demo-user-option-active" : ""}`}
                      onClick={() => {
                        setOpen(false);
                        setSearch("");
                        if (!isSelected) {
                          void switchUser(item.user_id);
                        }
                      }}
                    >
                      <div className="demo-user-main">
                        <div className="demo-user-row-top">
                          <span className="demo-user-name">{item.display_name}</span>
                          <span className={`role-chip role-chip-${item.role}`}>{formatRoleLabel(item.role)}</span>
                        </div>
                        <span className="demo-user-sub">
                          {item.user_id} • {item.amministrazione}
                        </span>
                      </div>
                      {isSelected && <Check size={15} className="demo-check" aria-hidden="true" />}
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
