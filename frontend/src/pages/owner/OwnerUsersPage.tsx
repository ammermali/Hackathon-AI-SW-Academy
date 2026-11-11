import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Search, UserCheck, X } from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  StatusBadge,
} from "../../components/common/PlatformPrimitives";
import { useAuth } from "../../context/AuthContext";
import { getOwnerUserDetail, listOwnerUsers } from "../../services/ownerApi";
import type { OwnerUserDetail, OwnerUsersPage as OwnerUsersPageData } from "../../types/platform";
import { formatItalianDate } from "../../utils/courseHelpers";

function overallStatusTone(status: string): "success" | "info" | "warning" | "danger" | "neutral" {
  const s = status.toUpperCase();
  if (s === "EXCELLENT" || s === "GOOD") return "success";
  if (s === "ON_TRACK" || s === "ACTIVE") return "info";
  if (s === "NEEDS_ATTENTION" || s === "WARNING") return "warning";
  if (s === "CRITICAL" || s === "AT_RISK") return "danger";
  return "neutral";
}

export function OwnerUsersPage() {
  const { authContext, contextVersion } = useAuth();

  const [search, setSearch] = useState("");
  const [adminFilter, setAdminFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortBy, setSortBy] = useState("quiz_success_rate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const [usersPage, setUsersPage] = useState<OwnerUsersPageData | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<OwnerUserDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await listOwnerUsers(authContext, {
        search: search.trim() || undefined,
        amministrazione: adminFilter.trim() || undefined,
        learning_status: statusFilter || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: 15,
      });
      setUsersPage(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nel caricamento degli utenti.");
    } finally {
      setIsLoading(false);
    }
  }, [adminFilter, authContext, page, search, sortBy, sortDir, statusFilter]);

  useEffect(() => {
    setSelectedDetail(null);
    void loadUsers();
  }, [contextVersion, loadUsers]);

  const handleOpenUserDetail = async (userId: string) => {
    setIsLoadingDetail(true);
    setError(null);
    try {
      const detail = await getOwnerUserDetail(authContext, userId);
      setSelectedDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile caricare il dettaglio utente.");
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const totalPages = usersPage ? Math.max(1, Math.ceil(usersPage.total / usersPage.page_size)) : 1;

  return (
    <div className="page-container">
      <div className="breadcrumb-row">
        <Link to="/owner" className="back-link">
          <ArrowLeft size={15} /> Torna a Owner Dashboard
        </Link>
      </div>

      <div className="page-header">
        <div>
          <h1>Users Analytics</h1>
          <p>Monitoraggio individuale di progressi, quiz e lacune per ogni utente del tenant.</p>
        </div>
      </div>

      <section className="filter-bar" aria-label="Filtri utenti">
        <div className="filter-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setPage(1);
              setSearch(e.target.value);
            }}
            placeholder="Cerca utente o amministrazione..."
          />
        </div>

        <input
          type="text"
          className="filter-input"
          value={adminFilter}
          onChange={(e) => {
            setPage(1);
            setAdminFilter(e.target.value);
          }}
          placeholder="Amministrazione..."
          aria-label="Filtra amministrazione"
        />

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          aria-label="Ordina per"
        >
          <option value="quiz_success_rate">Ordina: Successo Quiz</option>
          <option value="open_gaps_count">Ordina: Lacune aperte</option>
          <option value="courses_completed">Ordina: Corsi completati</option>
          <option value="last_activity_at">Ordina: Ultima attività</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => {
            setPage(1);
            setStatusFilter(e.target.value);
          }}
          aria-label="Filtra stato apprendimento"
        >
          <option value="">Tutti gli stati</option>
          <option value="CRITICAL">Critico</option>
          <option value="NEEDS_ATTENTION">Richiede attenzione</option>
          <option value="ON_TRACK">In linea</option>
          <option value="EXCELLENT">Ottimo</option>
        </select>

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
        >
          Direzione: {sortDir === "desc" ? "↓ Decr." : "↑ Cresc."}
        </button>
      </section>

      {error && <ErrorBanner message={error} onRetry={() => void loadUsers()} />}

      <div className={selectedDetail ? "owner-split-grid" : ""}>
        <section className="panel-card">
          {isLoading ? (
            <LoadingState label="Caricamento utenti..." />
          ) : !usersPage || usersPage.items.length === 0 ? (
            <div className="empty-card">
              <p>Nessun utente trovato con i filtri selezionati.</p>
            </div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Utente</th>
                      <th>Amministrazione</th>
                      <th>Stato</th>
                      <th>Corsi compl.</th>
                      <th>Quiz success</th>
                      <th>Custom quiz</th>
                      <th>Lacune aperte</th>
                      <th>Ultima attività</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersPage.items.map((u) => (
                      <tr key={u.user_id}>
                        <td>
                          <strong>{u.display_name}</strong>
                          <div className="muted-meta">{u.user_id}</div>
                        </td>
                        <td>{u.amministrazione || "—"}</td>
                        <td>
                          <StatusBadge tone={overallStatusTone(u.overall_status)}>
                            {u.overall_status}
                          </StatusBadge>
                        </td>
                        <td>{u.courses_completed}</td>
                        <td>{u.quiz_success_rate.toFixed(1)}%</td>
                        <td>{u.custom_quizzes_count}</td>
                        <td>
                          {u.open_gaps_count}{" "}
                          {u.critical_gaps_count > 0 && (
                            <StatusBadge tone="danger">
                              {u.critical_gaps_count} crit.
                            </StatusBadge>
                          )}
                        </td>
                        <td>{formatItalianDate(u.last_activity_at, true)}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            onClick={() => void handleOpenUserDetail(u.user_id)}
                          >
                            Dettaglio
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {totalPages > 1 && (
                <div className="pagination-row">
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Precedente
                  </button>
                  <span>
                    Pagina {page} di {totalPages} ({usersPage.total} utenti)
                  </span>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Successiva
                  </button>
                </div>
              )}
            </>
          )}
        </section>

        {(selectedDetail || isLoadingDetail) && (
          <aside className="panel-card detail-drawer-card" aria-label="Dettaglio utente">
            {isLoadingDetail ? (
              <LoadingState label="Caricamento profilo utente..." />
            ) : (
              selectedDetail && (
                <div className="stack-md">
                  <div className="panel-card-header">
                    <div>
                      <div className="user-title-inline">
                        <UserCheck size={18} />
                        <h2>{selectedDetail.display_name}</h2>
                      </div>
                      <p className="muted-meta">
                        {selectedDetail.user_id} • {selectedDetail.amministrazione || "N/D"}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => setSelectedDetail(null)}
                      aria-label="Chiudi dettaglio"
                    >
                      <X size={16} />
                    </button>
                  </div>

                  <div>
                    <StatusBadge tone={overallStatusTone(selectedDetail.overall_status)}>
                      Stato: {selectedDetail.overall_status}
                    </StatusBadge>
                    {selectedDetail.learning_performance.retention_rate != null && (
                      <span className="muted-meta" style={{ marginLeft: "0.6rem" }}>
                        Retention: {selectedDetail.learning_performance.retention_rate.toFixed(1)}%
                      </span>
                    )}
                  </div>

                  <div>
                    <h3>Lacune conoscitive ({selectedDetail.knowledge_gaps.length})</h3>
                    {selectedDetail.knowledge_gaps.length === 0 ? (
                      <p className="muted-meta">Nessuna lacuna registrata.</p>
                    ) : (
                      <ul className="topic-list">
                        {selectedDetail.knowledge_gaps.map((gap) => (
                          <li key={gap.gap_id} className="topic-list-item">
                            <div className="gap-row-top">
                              <strong>{gap.topic}</strong>
                              <StatusBadge
                                tone={
                                  gap.criticality === "CRITICAL" || gap.criticality === "HIGH"
                                    ? "danger"
                                    : "warning"
                                }
                              >
                                {gap.criticality}
                              </StatusBadge>
                            </div>
                            <span className="muted-meta">
                              {gap.software} • {gap.status} • Errori: {gap.error_count}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div>
                    <h3>Storico recente ({selectedDetail.learning_history.length})</h3>
                    {selectedDetail.learning_history.length === 0 ? (
                      <p className="muted-meta">Nessun evento recente.</p>
                    ) : (
                      <ul className="topic-list">
                        {selectedDetail.learning_history.slice(0, 8).map((ev, i) => (
                          <li key={i} className="topic-list-item">
                            <strong>{ev.title}</strong>
                            <span className="muted-meta">
                              {ev.result_summary} • {formatItalianDate(ev.occurred_at, true)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
