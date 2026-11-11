import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, AlertTriangle, X } from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  StatusBadge,
} from "../../components/common/PlatformPrimitives";
import { useAuth } from "../../context/AuthContext";
import { getTopicUsersDrilldown, listOwnerTopicsToReview } from "../../services/ownerApi";
import type { OwnerTopicDrilldown, OwnerTopicReviewItem } from "../../types/platform";
import { formatItalianDate } from "../../utils/courseHelpers";

function criticalityTone(c: string): "danger" | "warning" | "info" | "neutral" {
  if (c === "CRITICAL") return "danger";
  if (c === "HIGH" || c === "MEDIUM") return "warning";
  return "info";
}

export function OwnerTopicsPage() {
  const { authContext, contextVersion } = useAuth();

  const [softwareFilter, setSoftwareFilter] = useState("");
  const [adminFilter, setAdminFilter] = useState("");
  const [criticalityFilter, setCriticalityFilter] = useState("");

  const [topics, setTopics] = useState<OwnerTopicReviewItem[]>([]);
  const [drilldown, setDrilldown] = useState<OwnerTopicDrilldown | null>(null);
  const [isLoadingDrilldown, setIsLoadingDrilldown] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTopics = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const items = await listOwnerTopicsToReview(authContext, {
        software: softwareFilter.trim() || undefined,
        amministrazione: adminFilter.trim() || undefined,
        criticality: criticalityFilter || undefined,
      });
      setTopics(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nel caricamento degli argomenti.");
    } finally {
      setIsLoading(false);
    }
  }, [adminFilter, authContext, criticalityFilter, softwareFilter]);

  useEffect(() => {
    setDrilldown(null);
    void loadTopics();
  }, [contextVersion, loadTopics]);

  const handleOpenDrilldown = async (topicName: string) => {
    setIsLoadingDrilldown(true);
    setError(null);
    try {
      const data = await getTopicUsersDrilldown(
        authContext,
        topicName,
        adminFilter.trim() || undefined
      );
      setDrilldown(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile caricare gli utenti coinvolti.");
    } finally {
      setIsLoadingDrilldown(false);
    }
  };

  return (
    <div className="page-container">
      <div className="breadcrumb-row">
        <Link to="/owner" className="back-link">
          <ArrowLeft size={15} /> Torna a Owner Dashboard
        </Link>
      </div>

      <div className="page-header">
        <div>
          <h1>Topics to Review</h1>
          <p>
            Argomenti più critici o soggetti ad errori ripetuti, con drilldown sugli operatori
            coinvolti.
          </p>
        </div>
      </div>

      <section className="filter-bar" aria-label="Filtri argomenti da rivedere">
        <input
          type="text"
          className="filter-input"
          value={softwareFilter}
          onChange={(e) => setSoftwareFilter(e.target.value)}
          placeholder="Filtra software..."
          aria-label="Filtra software"
        />

        <input
          type="text"
          className="filter-input"
          value={adminFilter}
          onChange={(e) => setAdminFilter(e.target.value)}
          placeholder="Filtra amministrazione..."
          aria-label="Filtra amministrazione"
        />

        <select
          value={criticalityFilter}
          onChange={(e) => setCriticalityFilter(e.target.value)}
          aria-label="Filtra criticità"
        >
          <option value="">Tutte le criticità</option>
          <option value="CRITICAL">CRITICAL</option>
          <option value="HIGH">HIGH</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="LOW">LOW</option>
        </select>
      </section>

      {error && <ErrorBanner message={error} onRetry={() => void loadTopics()} />}

      <div className={drilldown || isLoadingDrilldown ? "owner-split-grid" : ""}>
        <section className="panel-card">
          {isLoading ? (
            <LoadingState label="Analisi topic critici..." />
          ) : topics.length === 0 ? (
            <div className="empty-card">
              <AlertTriangle size={22} aria-hidden="true" />
              <p>Nessun argomento critico rilevato per i filtri selezionati.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Argomento</th>
                    <th>Software / Modulo</th>
                    <th>Criticità</th>
                    <th>Utenti coinvolti</th>
                    <th>Lacune aperte</th>
                    <th>Error rate medio</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {topics.map((item) => (
                    <tr key={`${item.software}-${item.topic}`}>
                      <td>
                        <strong>{item.topic}</strong>
                      </td>
                      <td>
                        {item.software} • <span className="muted-meta">{item.module_name}</span>
                      </td>
                      <td>
                        <StatusBadge tone={criticalityTone(item.criticality)}>
                          {item.criticality}
                        </StatusBadge>
                      </td>
                      <td>{item.affected_users_count}</td>
                      <td>
                        {item.open_gaps_count}/{item.total_gaps_count}
                      </td>
                      <td>{item.avg_error_rate.toFixed(1)}%</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => void handleOpenDrilldown(item.topic)}
                        >
                          Vedi utenti
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {(drilldown || isLoadingDrilldown) && (
          <aside className="panel-card detail-drawer-card" aria-label="Utenti coinvolti per topic">
            {isLoadingDrilldown ? (
              <LoadingState label="Caricamento drilldown topic..." />
            ) : (
              drilldown && (
                <div className="stack-md">
                  <div className="panel-card-header">
                    <div>
                      <h2>{drilldown.topic_summary.topic}</h2>
                      <p className="muted-meta">
                        {drilldown.topic_summary.software} • {drilldown.topic_summary.module_name}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => setDrilldown(null)}
                      aria-label="Chiudi drilldown"
                    >
                      <X size={16} />
                    </button>
                  </div>

                  <h3>Operatori coinvolti ({drilldown.affected_users.length})</h3>
                  {drilldown.affected_users.length === 0 ? (
                    <p className="muted-meta">Nessun utente elencato per questo filtro.</p>
                  ) : (
                    <ul className="topic-list">
                      {drilldown.affected_users.map((au) => (
                        <li key={au.user_id} className="topic-list-item">
                          <div className="gap-row-top">
                            <strong>{au.display_name}</strong>
                            <StatusBadge tone={criticalityTone(au.priority)}>
                              {au.gap_status}
                            </StatusBadge>
                          </div>
                          <span className="muted-meta">
                            {au.amministrazione} • Errori ripetuti: {au.repeated_error_count} •
                            Ultima verifica: {formatItalianDate(au.last_verified_at)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
