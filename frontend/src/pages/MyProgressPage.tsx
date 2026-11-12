import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Award, CheckCircle2, Flame, ShieldAlert, TrendingUp } from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  ScoreBarChart,
  StatCard,
  StatusBadge,
  type ChartPoint,
} from "../components/common/PlatformPrimitives";
import { useAuth } from "../context/AuthContext";
import { getUserLearningOverview } from "../services/academyApi";
import { getLearningMetrics, getLearningProfile } from "../services/customQuizApi";
import type {
  LearningMetrics,
  TopicProfileItem,
  UserLearningOverview,
  UserLearningProfile,
} from "../types/platform";
import { formatItalianDate } from "../utils/courseHelpers";

function classifyTopicBucket(item: TopicProfileItem): "learned" | "consolidating" | "to_improve" {
  const stage = item.learning_stage.toUpperCase();
  if (stage === "KNOWN" || stage === "MASTERED") return "learned";
  if (stage === "CONSOLIDATING" || stage === "INITIAL") return "consolidating";
  return "to_improve";
}

export function MyProgressPage() {
  const { authContext, contextVersion, user } = useAuth();
  const [metrics, setMetrics] = useState<LearningMetrics | null>(null);
  const [profile, setProfile] = useState<UserLearningProfile | null>(null);
  const [overview, setOverview] = useState<UserLearningOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProgress = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [metricsData, profileData, overviewData] = await Promise.all([
        getLearningMetrics(authContext, user.userId),
        getLearningProfile(authContext, user.userId),
        getUserLearningOverview(authContext, user.userId),
      ]);
      setMetrics(metricsData);
      setProfile(profileData);
      setOverview(overviewData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile caricare i progressi.");
    } finally {
      setIsLoading(false);
    }
  }, [authContext, user.userId]);

  useEffect(() => {
    void loadProgress();
  }, [contextVersion, loadProgress]);

  const chartPoints = useMemo<ChartPoint[]>(() => {
    const coursePoints = (overview?.course_quiz_attempts ?? []).map((a) => ({
      at: new Date(a.completed_at).getTime(),
      label: formatItalianDate(a.completed_at),
      value: a.percentage,
      sublabel: `Corso: ${a.quiz_title}`,
    }));
    const customPoints = (overview?.custom_quiz_attempts ?? []).map((a) => ({
      at: new Date(a.completed_at).getTime(),
      label: formatItalianDate(a.completed_at),
      value: a.percentage,
      sublabel: `Custom: ${a.topics_verified.slice(0, 2).join(", ") || a.module_name}`,
    }));
    return [...coursePoints, ...customPoints]
      .sort((a, b) => a.at - b.at)
      .slice(-10)
      .map(({ label, value, sublabel }) => ({ label, value, sublabel }));
  }, [overview]);

  const topicBuckets = useMemo(() => {
    const learned: TopicProfileItem[] = [];
    const consolidating: TopicProfileItem[] = [];
    const toImprove: TopicProfileItem[] = [];

    for (const tp of profile?.topic_profiles ?? []) {
      const bucket = classifyTopicBucket(tp);
      if (bucket === "learned") learned.push(tp);
      else if (bucket === "consolidating") consolidating.push(tp);
      else toImprove.push(tp);
    }
    return { learned, consolidating, toImprove };
  }, [profile]);

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>I miei progressi</h1>
          <p>
            Analisi delle competenze acquisite, accuratezza nei quiz e stato delle lacune per{" "}
            <strong>{user.displayName}</strong>.
          </p>
        </div>
        <Link to="/my-learning" className="btn btn-primary">
          Vai ai quiz personalizzati
        </Link>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => void loadProgress()} />}

      {isLoading ? (
        <LoadingState label="Elaborazione metriche di apprendimento..." />
      ) : (
        <div className="stack-lg">
          <div className="stats-grid">
            <StatCard
              label="Progresso apprendimento"
              value={`${(metrics?.learning_progress ?? 0).toFixed(1)}%`}
              hint={`${overview?.completed_lesson_ids.length ?? 0} lezioni completate`}
              tone="accent"
              icon={<Award size={17} />}
            />
            <StatCard
              label="Accuratezza quiz"
              value={`${(metrics?.quiz_accuracy ?? 0).toFixed(1)}%`}
              hint={`${metrics?.attempts_count ?? 0} verifiche custom registrate`}
              tone="success"
              icon={<CheckCircle2 size={17} />}
            />
            <StatCard
              label="Miglioramento"
              value={
                metrics?.learning_improvement != null
                  ? `${metrics.learning_improvement > 0 ? "+" : ""}${metrics.learning_improvement.toFixed(1)}%`
                  : "N/D"
              }
              hint="Variazione rispetto ai tentativi iniziali"
              icon={<TrendingUp size={17} />}
            />
            <StatCard
              label="Risoluzione lacune"
              value={`${(metrics?.knowledge_gap_resolution_rate ?? 0).toFixed(1)}%`}
              hint={
                metrics?.retention_rate != null
                  ? `Retention: ${metrics.retention_rate.toFixed(1)}%`
                  : `Errori ripetuti: ${(metrics?.repeated_error_rate ?? 0).toFixed(1)}%`
              }
              icon={<Flame size={17} />}
            />
          </div>

          <ScoreBarChart
            title="Andamento punteggi nei quiz (cronologico)"
            points={chartPoints}
            emptyText="Completa almeno un quiz didattico o un Custom Quiz per visualizzare il grafico."
          />

          <div className="three-col-grid">
            <section className="panel-card">
              <div className="panel-card-header">
                <h2>Appresi</h2>
                <StatusBadge tone="success">
                  {topicBuckets.learned.length || profile?.known_topics.length || 0}
                </StatusBadge>
              </div>
              {topicBuckets.learned.length === 0 && (profile?.known_topics.length ?? 0) === 0 ? (
                <p className="muted-meta">Nessun argomento consolidato come appreso finora.</p>
              ) : (
                <ul className="topic-list">
                  {topicBuckets.learned.map((tp) => (
                    <li key={`${tp.software}-${tp.topic}`} className="topic-list-item">
                      <strong>{tp.topic}</strong>
                      <span className="muted-meta">
                        Livello {(tp.estimated_level * 100).toFixed(0)}% • {tp.correct_count}/
                        {tp.verification_count} corrette
                      </span>
                    </li>
                  ))}
                  {topicBuckets.learned.length === 0 &&
                    profile?.known_topics.map((topic) => (
                      <li key={topic} className="topic-list-item">
                        <strong>{topic}</strong>
                      </li>
                    ))}
                </ul>
              )}
            </section>

            <section className="panel-card">
              <div className="panel-card-header">
                <h2>In consolidamento</h2>
                <StatusBadge tone="info">{topicBuckets.consolidating.length}</StatusBadge>
              </div>
              {topicBuckets.consolidating.length === 0 ? (
                <p className="muted-meta">Nessun argomento attualmente in fase intermedia.</p>
              ) : (
                <ul className="topic-list">
                  {topicBuckets.consolidating.map((tp) => (
                    <li key={`${tp.software}-${tp.topic}`} className="topic-list-item">
                      <strong>{tp.topic}</strong>
                      <span className="muted-meta">
                        Stage: {tp.learning_stage} • Query RAG: {tp.rag_query_count}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="panel-card">
              <div className="panel-card-header">
                <h2>Da approfondire</h2>
                <StatusBadge tone="warning">
                  {Math.max(topicBuckets.toImprove.length, profile?.open_gaps.length ?? 0)}
                </StatusBadge>
              </div>
              {(profile?.open_gaps.length ?? 0) === 0 && topicBuckets.toImprove.length === 0 ? (
                <p className="muted-meta">Ottimo: nessuna lacuna aperta rilevata!</p>
              ) : (
                <ul className="topic-list">
                  {(profile?.open_gaps ?? []).map((gap) => (
                    <li key={gap.id} className="topic-list-item topic-list-item-warn">
                      <div className="gap-row-top">
                        <strong>{gap.topic}</strong>
                        <StatusBadge tone={gap.priority === "CRITICAL" || gap.priority === "HIGH" ? "danger" : "warning"}>
                          {gap.priority}
                        </StatusBadge>
                      </div>
                      <span className="muted-meta">
                        {gap.software} • Errori ripetuti: {gap.repeated_error_count} • Confidenza:{" "}
                        {(gap.confidence * 100).toFixed(0)}%
                      </span>
                    </li>
                  ))}
                  {topicBuckets.toImprove
                    .filter((tp) => !(profile?.open_gaps ?? []).some((g) => g.topic === tp.topic))
                    .map((tp) => (
                      <li key={`${tp.software}-${tp.topic}`} className="topic-list-item topic-list-item-warn">
                        <strong>{tp.topic}</strong>
                        <span className="muted-meta">
                          Stage: {tp.learning_stage} • Errori: {tp.error_count}
                        </span>
                      </li>
                    ))}
                </ul>
              )}
            </section>
          </div>

          {(profile?.frequent_questions.length ?? 0) > 0 && (
            <section className="panel-card">
              <div className="panel-card-header">
                <h2>Domande frequenti inviate a Operator Copilot</h2>
                <ShieldAlert size={16} aria-hidden="true" />
              </div>
              <div className="tag-row">
                {profile!.frequent_questions.map((fq, idx) => (
                  <span key={idx} className="topic-chip">
                    {fq}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
