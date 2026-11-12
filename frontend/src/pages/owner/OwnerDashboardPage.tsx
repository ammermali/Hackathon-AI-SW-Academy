import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  ScoreBarChart,
  StatCard,
  StatusBadge,
  type ChartPoint,
} from "../../components/common/PlatformPrimitives";
import { useAuth } from "../../context/AuthContext";
import {
  getOwnerCustomQuizAnalytics,
  getOwnerInsights,
  getOwnerOverview,
} from "../../services/ownerApi";
import type {
  OwnerCustomQuizAnalytics,
  OwnerInsightsResponse,
  OwnerOverview,
} from "../../types/platform";

export function OwnerDashboardPage() {
  const { authContext, contextVersion } = useAuth();

  const [softwareFilter, setSoftwareFilter] = useState("");
  const [adminFilter, setAdminFilter] = useState("");
  const [useQwenInsights, setUseQwenInsights] = useState(false);

  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  const [customAnalytics, setCustomAnalytics] = useState<OwnerCustomQuizAnalytics | null>(null);
  const [insights, setInsights] = useState<OwnerInsightsResponse | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingInsights, setIsLoadingInsights] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(
    async (refreshSnapshot = false) => {
      setIsLoading(true);
      setError(null);
      const filters = {
        software: softwareFilter || undefined,
        amministrazione: adminFilter || undefined,
      };
      try {
        const [ov, cq, ins] = await Promise.all([
          getOwnerOverview(authContext, { ...filters, refresh: refreshSnapshot }),
          getOwnerCustomQuizAnalytics(authContext, filters),
          getOwnerInsights(authContext, { ...filters, use_llm_synthesis: useQwenInsights }),
        ]);
        setOverview(ov);
        setCustomAnalytics(cq);
        setInsights(ins);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Errore nel caricamento dell'Owner Dashboard."
        );
      } finally {
        setIsLoading(false);
      }
    },
    [adminFilter, authContext, softwareFilter, useQwenInsights]
  );

  useEffect(() => {
    void loadDashboard(false);
  }, [contextVersion, loadDashboard]);

  const handleToggleQwenInsights = async () => {
    const nextFlag = !useQwenInsights;
    setUseQwenInsights(nextFlag);
    setIsLoadingInsights(true);
    try {
      const ins = await getOwnerInsights(authContext, {
        software: softwareFilter || undefined,
        amministrazione: adminFilter || undefined,
        use_llm_synthesis: nextFlag,
      });
      setInsights(ins);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nella generazione insights.");
    } finally {
      setIsLoadingInsights(false);
    }
  };

  const timelinePoints = useMemo<ChartPoint[]>(
    () =>
      (overview?.timeline ?? []).map((pt) => ({
        label: pt.period,
        value: pt.avg_score,
        sublabel: `${pt.attempts} tentativi • ${pt.gaps_resolved} lacune risolte`,
      })),
    [overview]
  );

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <div className="hero-eyebrow">
            <span>Area Learning Manager • Governance Formativa</span>
          </div>
          <h1>Dashboard Learning Manager</h1>
          <p>
            Monitoraggio aggregato dell&apos;apprendimento, performance quiz personalizzati e criticità
            organizzative.
          </p>
        </div>

        <div className="header-actions-row">
          <Link to="/owner/users" className="btn btn-secondary">
            Analisi utenti
          </Link>
          <Link to="/owner/topics" className="btn btn-secondary">
            Argomenti da rivedere
          </Link>
          <button
            type="button"
            className="btn btn-primary"
            disabled={isLoading}
            onClick={() => void loadDashboard(true)}
          >
            <RefreshCw size={15} className={isLoading ? "spin" : ""} aria-hidden="true" />
            <span>Aggiorna snapshot</span>
          </button>
        </div>
      </div>

      <section className="filter-bar" aria-label="Filtri dashboard Owner">
        <select
          value={softwareFilter}
          onChange={(e) => setSoftwareFilter(e.target.value)}
          aria-label="Filtra per software"
        >
          <option value="">Tutti i software</option>
          {(overview?.available_softwares ?? []).map((sw) => (
            <option key={sw} value={sw}>
              {sw}
            </option>
          ))}
        </select>

        <select
          value={adminFilter}
          onChange={(e) => setAdminFilter(e.target.value)}
          aria-label="Filtra per amministrazione"
        >
          <option value="">Tutte le amministrazioni</option>
          {(overview?.available_administrations ?? []).map((adm) => (
            <option key={adm} value={adm}>
              {adm}
            </option>
          ))}
        </select>
      </section>

      {error && <ErrorBanner message={error} onRetry={() => void loadDashboard(false)} />}

      {isLoading && !overview ? (
        <LoadingState label="Calcolo KPI Learning Analytics..." />
      ) : (
        overview && (
          <div className="stack-lg">
            <section aria-label="Indicatori principali Owner">
              <div className="stats-grid stats-grid-3">
                <StatCard
                  label="Utenti monitorati"
                  value={overview.total_users}
                  hint={`${overview.active_users_in_period} attivi nel periodo`}
                  icon={<Users size={17} />}
                />
                <StatCard
                  label="Completamento corsi"
                  value={`${overview.course_completion_rate.toFixed(1)}%`}
                  tone="accent"
                  icon={<CheckCircle2 size={17} />}
                />
                <StatCard
                  label="Media punteggi quiz"
                  value={`${overview.avg_quiz_score.toFixed(1)}%`}
                  tone="success"
                  icon={<Activity size={17} />}
                />
                <StatCard
                  label="Miglioramento apprendimento"
                  value={
                    overview.avg_learning_improvement != null
                      ? `${overview.avg_learning_improvement > 0 ? "+" : ""}${overview.avg_learning_improvement.toFixed(1)}%`
                      : "N/D"
                  }
                  icon={<TrendingUp size={17} />}
                />
                <StatCard
                  label="Risoluzione lacune"
                  value={`${overview.knowledge_gap_resolution_rate.toFixed(1)}%`}
                  tone="success"
                  icon={<ShieldCheck size={17} />}
                />
                <StatCard
                  label="Lacune aperte"
                  value={overview.open_gaps_count}
                  hint={`${overview.users_with_critical_gaps} utenti con lacune critiche`}
                  tone={overview.users_with_critical_gaps > 0 ? "warning" : "default"}
                  icon={<AlertTriangle size={17} />}
                />
              </div>
            </section>

            <ScoreBarChart
              title="Andamento medio punteggi nel tempo"
              points={timelinePoints}
              emptyText="Ancora nessun trend temporale disponibile per i filtri selezionati."
            />

            {customAnalytics && (
              <section className="panel-card">
                <div className="panel-card-header">
                  <h2>Performance quiz personalizzati adattivi</h2>
                  <StatusBadge tone="info">
                    {customAnalytics.total_completed}/{customAnalytics.total_generated} completati
                  </StatusBadge>
                </div>
                <div className="stats-grid">
                  <StatCard
                    label="Media risposte corrette"
                    value={`${customAnalytics.avg_correct_percentage.toFixed(1)}%`}
                    tone="accent"
                  />
                  <StatCard
                    label="Lacune risolte via follow-up"
                    value={customAnalytics.gaps_resolved_via_followup}
                    tone="success"
                  />
                  <StatCard
                    label="Lacune persistenti"
                    value={customAnalytics.persistent_gaps_count}
                    tone={customAnalytics.persistent_gaps_count > 0 ? "warning" : "default"}
                  />
                  <StatCard
                    label="Tasso errori ripetuti"
                    value={`${customAnalytics.repeated_error_rate.toFixed(1)}%`}
                    hint={
                      customAnalytics.retention_rate != null
                        ? `Retention: ${customAnalytics.retention_rate.toFixed(1)}%`
                        : undefined
                    }
                  />
                </div>
              </section>
            )}

            {insights && (
              <section className="panel-card">
                <div className="panel-card-header">
                  <div>
                    <h2>Executive Insights & Raccomandazioni</h2>
                    <p className="muted-meta">Motore: {insights.model_used}</p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={isLoadingInsights}
                    onClick={() => void handleToggleQwenInsights()}
                  >
                    {useQwenInsights ? <Brain size={15} /> : <Sparkles size={15} />}
                    <span>
                      {isLoadingInsights
                        ? "Sintesi in corso..."
                        : useQwenInsights
                          ? "Usa motore deterministico"
                          : "Sintetizza con Qwen"}
                    </span>
                  </button>
                </div>

                {insights.insights.length === 0 ? (
                  <p className="muted-meta">Nessun insight rilevato per i filtri correnti.</p>
                ) : (
                  <div className="insights-list">
                    {insights.insights.map((ins, idx) => (
                      <div key={idx} className="insight-card">
                        <div className="insight-head">
                          <StatusBadge
                            tone={
                              ins.severity === "CRITICAL" || ins.severity === "HIGH"
                                ? "danger"
                                : ins.severity === "MEDIUM"
                                  ? "warning"
                                  : "info"
                            }
                          >
                            {ins.severity} • {ins.category}
                          </StatusBadge>
                          <StatusBadge tone="neutral">{ins.source_engine}</StatusBadge>
                        </div>
                        <p className="insight-message">{ins.message}</p>
                        <p className="insight-action">
                          <strong>Azione consigliata:</strong> {ins.recommended_action}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
          </div>
        )
      )}
    </div>
  );
}
