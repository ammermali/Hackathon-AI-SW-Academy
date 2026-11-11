import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { PlatformSidebar } from "./PlatformSidebar";
import { TopHeader } from "./TopHeader";

export function AppLayout() {
  const { isOwner, switchError, clearSwitchError } = useAuth();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Safely leave Owner routes when switching to a non-Owner profile in Demo Mode
  useEffect(() => {
    if (!isOwner && location.pathname.startsWith("/owner")) {
      navigate("/", { replace: true });
    }
  }, [isOwner, location.pathname, navigate]);

  return (
    <div className="platform-shell">
      <PlatformSidebar
        isCollapsed={isSidebarCollapsed}
        isMobileOpen={isMobileSidebarOpen}
        onCollapseDesktop={() => setIsSidebarCollapsed(true)}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      <div className="platform-workspace">
        <TopHeader
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleDesktopSidebar={() => setIsSidebarCollapsed(false)}
          onOpenMobileSidebar={() => setIsMobileSidebarOpen(true)}
        />

        {switchError && (
          <div className="global-error-banner" role="alert">
            <div className="global-error-text">
              <AlertCircle size={16} aria-hidden="true" />
              <span>{switchError}</span>
            </div>
            <button type="button" className="icon-button" onClick={clearSwitchError} aria-label="Chiudi avviso">
              <X size={16} />
            </button>
          </div>
        )}

        <main className="platform-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
