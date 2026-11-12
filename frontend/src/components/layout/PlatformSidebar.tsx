import { NavLink } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Bot,
  Database,
  Home,
  LayoutDashboard,
  ListChecks,
  Users,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

interface PlatformSidebarProps {
  isCollapsed: boolean;
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

export function PlatformSidebar({
  isCollapsed,
  isMobileOpen,
  onCloseMobile,
}: PlatformSidebarProps) {
  const { isOwner, isKnowledgeManager } = useAuth();

  const mainNav = [
    { to: "/", label: "Home", icon: Home, end: true },
    { to: "/assistant", label: "Operator Copilot", icon: Bot, end: false },
    { to: "/learning", label: "Area Formazione", icon: BookOpen, end: false },
    { to: "/my-learning", label: "La mia formazione", icon: ListChecks, end: false },
    { to: "/my-progress", label: "I miei progressi", icon: BarChart3, end: false },
  ];

  const ownerNav = [
    { to: "/owner", label: "Dashboard Learning Manager", icon: LayoutDashboard, end: true },
    { to: "/owner/users", label: "Analisi utenti", icon: Users, end: false },
    { to: "/owner/topics", label: "Argomenti da rivedere", icon: AlertTriangle, end: false },
  ];

  return (
    <>
      {isMobileOpen && <div className="sidebar-backdrop mobile-only" onClick={onCloseMobile} aria-hidden="true" />}

      <aside
        className={`platform-sidebar ${isCollapsed ? "platform-sidebar-collapsed" : ""} ${
          isMobileOpen ? "platform-sidebar-mobile-open" : ""
        }`}
        aria-label="Navigazione piattaforma AI Software Academy"
      >
        <div className="sidebar-top">
          <div className="brand-block">
            <div className="brand-logo" aria-hidden="true">
              <img src="/brand-logo.png" alt="" className="brand-logo-img" />
            </div>
            <div>
              <div className="brand-name">AI Software Academy</div>
            </div>
          </div>
        </div>

        <nav className="platform-nav" aria-label="Menu principale">
          <div className="nav-group-label">Piattaforma</div>
          <ul>
            {mainNav.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onCloseMobile}
                    className={({ isActive }) => `nav-link-item ${isActive ? "nav-link-active" : ""}`}
                  >
                    <Icon size={17} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>

          {isKnowledgeManager && (
            <>
              <div className="nav-group-label">Base di conoscenza</div>
              <ul>
                <li>
                  <NavLink
                    to="/knowledge-base"
                    onClick={onCloseMobile}
                    className={({ isActive }) => `nav-link-item ${isActive ? "nav-link-active" : ""}`}
                  >
                    <Database size={17} aria-hidden="true" />
                    <span>Gestione documenti</span>
                  </NavLink>
                </li>
              </ul>
            </>
          )}

          {isOwner && (
            <>
              <div className="nav-group-label nav-group-owner">Area Learning Manager</div>
              <ul>
                {ownerNav.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onCloseMobile}
                        className={({ isActive }) => `nav-link-item ${isActive ? "nav-link-active" : ""}`}
                      >
                        <Icon size={17} aria-hidden="true" />
                        <span>{item.label}</span>
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </nav>
      </aside>
    </>
  );
}
