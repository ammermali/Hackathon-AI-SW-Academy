import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { APP_CONFIG } from "../config/env";
import { checkHealth } from "../services/api";
import { getDemoStatus, listDemoUsers, switchDemoUser } from "../services/demoApi";
import type { DemoUserItem, RequestAuthContext } from "../types/platform";
import type { BackendStatus } from "../types/rag";

const DEMO_SESSION_KEY = "asa_demo_session";

export interface ActiveUserSession {
  tenantId: string;
  userId: string;
  displayName: string;
  role: string;
  amministrazione: string;
  softwaresUsed: string[];
  demoToken: string | null;
  isDemo: boolean;
}

interface AuthContextValue {
  user: ActiveUserSession;
  authContext: RequestAuthContext;
  contextVersion: number;
  demoModeEnabled: boolean;
  demoUsers: DemoUserItem[];
  isLoadingUsers: boolean;
  isSwitchingUser: boolean;
  switchError: string | null;
  backendStatus: BackendStatus;
  refreshHealth: () => Promise<void>;
  refreshDemoUsers: () => Promise<void>;
  switchUser: (targetUserId: string) => Promise<void>;
  clearSwitchError: () => void;
  isOwner: boolean;
  isKnowledgeManager: boolean;
}

const DEFAULT_SESSION: ActiveUserSession = {
  tenantId: "default",
  userId: APP_CONFIG.defaultUserId,
  displayName: APP_CONFIG.defaultUserId,
  role: "operatore",
  amministrazione: "Predefinita",
  softwaresUsed: [],
  demoToken: null,
  isDemo: false,
};

function loadSavedSession(): ActiveUserSession {
  try {
    const raw = window.sessionStorage.getItem(DEMO_SESSION_KEY);
    if (!raw) return DEFAULT_SESSION;
    const parsed = JSON.parse(raw) as Partial<ActiveUserSession>;
    if (parsed && typeof parsed.userId === "string" && parsed.userId.trim()) {
      return {
        ...DEFAULT_SESSION,
        ...parsed,
        userId: parsed.userId.trim(),
        softwaresUsed: Array.isArray(parsed.softwaresUsed) ? parsed.softwaresUsed : [],
      };
    }
  } catch {
    // Ignore storage read errors safely
  }
  return DEFAULT_SESSION;
}

function saveSession(next: ActiveUserSession): void {
  try {
    window.sessionStorage.setItem(DEMO_SESSION_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage write errors safely
  }
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ActiveUserSession>(loadSavedSession);
  const [contextVersion, setContextVersion] = useState(0);
  const [demoModeEnabled, setDemoModeEnabled] = useState(false);
  const [demoUsers, setDemoUsers] = useState<DemoUserItem[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isSwitchingUser, setIsSwitchingUser] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  const refreshHealth = useCallback(async () => {
    setBackendStatus("checking");
    try {
      await checkHealth();
      setBackendStatus("online");
    } catch {
      setBackendStatus("offline");
    }
  }, []);

  const applyDemoSwitch = useCallback(async (tenantId: string, targetUserId: string) => {
    const res = await switchDemoUser(tenantId, targetUserId);
    const next: ActiveUserSession = {
      tenantId: res.tenant_id,
      userId: res.user.user_id,
      displayName: res.user.display_name,
      role: res.user.role,
      amministrazione: res.user.amministrazione,
      softwaresUsed: res.user.softwares_used ?? [],
      demoToken: res.token,
      isDemo: true,
    };
    saveSession(next);
    setUser(next);
    setContextVersion((v) => v + 1);
  }, []);

  const refreshDemoUsers = useCallback(async () => {
    setIsLoadingUsers(true);
    try {
      const status = await getDemoStatus();
      setDemoModeEnabled(status.demo_mode_enabled);
      if (!status.demo_mode_enabled) {
        setDemoUsers([]);
        return;
      }

      const users = await listDemoUsers(user.tenantId);
      setDemoUsers(users);

      // Sync profile metadata for current user or auto-acquire server-signed demo token
      const matching = users.find((u) => u.user_id === user.userId);
      if (matching && !user.demoToken) {
        await applyDemoSwitch(user.tenantId, matching.user_id);
      } else if (!matching && users.length > 0 && !user.demoToken) {
        const preferred = users.find((u) => u.role === "operatore") ?? users[0];
        await applyDemoSwitch(user.tenantId, preferred.user_id);
      } else if (matching) {
        setUser((prev) => ({
          ...prev,
          displayName: matching.display_name,
          amministrazione: matching.amministrazione,
          softwaresUsed: matching.softwares_used,
        }));
      }
    } catch {
      // Keep UI functional even if backend demo endpoints are unreachable
    } finally {
      setIsLoadingUsers(false);
    }
  }, [applyDemoSwitch, user.demoToken, user.tenantId, user.userId]);

  useEffect(() => {
    void refreshHealth();
    void refreshDemoUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchUser = useCallback(
    async (targetUserId: string) => {
      if (!demoModeEnabled || isSwitchingUser) return;
      setIsSwitchingUser(true);
      setSwitchError(null);
      try {
        await applyDemoSwitch(user.tenantId, targetUserId);
        // Also refresh directory list for latest softwares_used
        const users = await listDemoUsers(user.tenantId);
        setDemoUsers(users);
      } catch (err) {
        setSwitchError(err instanceof Error ? err.message : "Errore durante il cambio utente demo.");
      } finally {
        setIsSwitchingUser(false);
      }
    },
    [applyDemoSwitch, demoModeEnabled, isSwitchingUser, user.tenantId]
  );

  const authContext: RequestAuthContext = {
    tenantId: user.tenantId,
    userId: user.userId,
    role: user.role,
    demoToken: user.demoToken,
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        authContext,
        contextVersion,
        demoModeEnabled,
        demoUsers,
        isLoadingUsers,
        isSwitchingUser,
        switchError,
        backendStatus,
        refreshHealth,
        refreshDemoUsers,
        switchUser,
        clearSwitchError: () => setSwitchError(null),
        isOwner: user.role === "owner" || user.role === "learning_manager",
        isKnowledgeManager: user.role === "knowledge_manager",
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve essere utilizzato all'interno di AuthProvider.");
  }
  return ctx;
}
