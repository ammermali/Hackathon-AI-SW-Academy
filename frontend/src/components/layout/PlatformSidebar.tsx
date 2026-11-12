import { NavLink } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Bot,
  Database,
  GraduationCap,
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
    { to: "/assistant", label: "AI Assistant", icon: Bot, end: false },
    { to: "/learning", label: "Learning Area", icon: BookOpen, end: false },
    { to: "/my-learning", label: "My Learning", icon: ListChecks, end: false },
    { to: "/my-progress", label: "My Progress", icon: BarChart3, end: false },
  ];

  const ownerNav = [
    { to: "/owner", label: "Owner Dashboard", icon: LayoutDashboard, end: true },
    { to: "/owner/users", label: "Users Analytics", icon: Users, end: false },
    { to: "/owner/topics", label: "Topics to Review", icon: AlertTriangle, end: false },
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
              <GraduationCap size={20} />
            </div>
            <div>
              <div className="brand-name">AI Software Academy</div>
              <div className="brand-sub">Formazione PA &amp; RAG</div>
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
              <div className="nav-group-label">Knowledge Base</div>
              <ul>
                <li>
                  <NavLink
                    to="/knowledge-base"
                    onClick={onCloseMobile}
                    className={({ isActive }) => `nav-link-item ${isActive ? "nav-link-active" : ""}`}
                  >
                    <Database size={17} aria-hidden="true" />
                    <span>Gestione KB</span>
                  </NavLink>
                </li>
              </ul>
            </>
          )}

          {isOwner && (
            <>
              <div className="nav-group-label nav-group-owner">Area Owner</div>
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

        <div className="platform-sidebar-footer">
          <span className="sidebar-version-note">Workspace RAG + LMS integrato</span>
        </div>
      </aside>
    </>
  );
}
