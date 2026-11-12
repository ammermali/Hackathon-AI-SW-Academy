import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  MessageSquareText,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  ProgressBar,
  StatCard,
  StatusBadge,
} from "../components/common/PlatformPrimitives";
import { useAuth } from "../context/AuthContext";
import { getUserLearningOverview, listCourses } from "../services/academyApi";
import { getLearningMetrics, getLearningProfile } from "../services/customQuizApi";
import type {
  Course,
  LearningMetrics,
  UserLearningOverview,
  UserLearningProfile,
} from "../types/platform";
import {
  countCourseLessons,
  formatCourseTypeLabel,
  formatProgressStatus,
  getCourseProgressForId,
  progressStatusTone,
} from "../utils/courseHelpers";

export function HomePage() {
  const { user, authContext, contextVersion } = useAuth();
  const [courses, setCourses] = useState<Course[]>([]);
  const [overview, setOverview] = useState<UserLearningOverview | null>(null);
  const [metrics, setMetrics] = useState<LearningMetrics | null>(null);
  const [profile, setProfile] = useState<UserLearningProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [coursesData, overviewData, metricsData, profileData] = await Promise.all([
        listCourses(authContext),
        getUserLearningOverview(authContext, user.userId),
        getLearningMetrics(authContext, user.userId),
        getLearningProfile(authContext, user.userId),
      ]);
      setCourses(coursesData);
      setOverview(overviewData);
      setMetrics(metricsData);
      setProfile(profileData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile caricare la panoramica personale.");
    } finally {
      setIsLoading(false);
    }
  }, [authContext, user.userId]);

  useEffect(() => {
    void loadData();
  }, [contextVersion, loadData]);

  const completedCoursesCount = useMemo(
    () =>
      courses.filter((c) => getCourseProgressForId(c, overview).status === "COMPLETED").length,
    [courses, overview]
  );

  const inProgressOrNext = useMemo(() => {
    const withProgress = courses.map((course) => ({
      course,
      progress: getCourseProgressForId(course, overview),
    }));
    const active = withProgress.filter((item) => item.progress.status === "IN_PROGRESS");
    const unstarted = withProgress.filter((item) => item.progress.status === "NOT_STARTED");
    return [...active, ...unstarted].slice(0, 3);
  }, [courses, overview]);

  const totalAttempts =
    (overview?.course_quiz_attempts.length ?? 0) + (overview?.custom_quiz_attempts.length ?? 0);

  return (
    <div className="page-container">
      <section className="hero-banner">
        <div className="hero-banner-content">
          <div className="hero-eyebrow">
            <span>{user.amministrazione || "Area Operativa"}</span>
            <span>•</span>
            <span>Profilo: {user.role === "owner" || user.role === "learning_manager" ? "learning manager" : user.role === "knowledge_manager" ? "knowledge manager" : user.role}</span>
          </div>
          <h1>Benvenuto, {user.displayName}</h1>
          <p>
            Consulta i manuali con Operator Copilot, segui i percorsi formativi generati dalla
            base di conoscenza e verifica i progressi con quiz mirati.
          </p>
        </div>
        <div className="hero-actions">
          <Link to="/assistant" className="btn btn-primary">
            <MessageSquareText size={16} aria-hidden="true" />
            <span>Apri Operator Copilot</span>
          </Link>
          <Link to="/learning" className="btn btn-secondary">
            <BookOpen size={16} aria-hidden="true" />
            <span>Esplora i corsi</span>
          </Link>
        </div>
      </section>

      {error && <ErrorBanner message={error} onRetry={() => void loadData()} />}

      <section aria-label="Azioni rapide">
        <h2 className="section-heading">Accesso rapido</h2>
        <div className="quick-access-grid">
          <Link to="/assistant" className="quick-card">
            <div className="quick-card-icon quick-icon-blue">
              <MessageSquareText size={20} />
            </div>
            <div className="quick-card-body">
              <h3>Chiedi a Operator Copilot</h3>
              <p>Interroga i manuali operativi e consulta le fonti citate.</p>
            </div>
            <ArrowRight size={16} className="quick-card-arrow" />
          </Link>

          <Link to="/learning" className="quick-card">
            <div className="quick-card-icon quick-icon-teal">
              <BookOpen size={20} />
            </div>
            <div className="quick-card-body">
              <h3>Vai all&apos;Area Formazione</h3>
              <p>{courses.length} percorsi formativi disponibili per il tuo ruolo.</p>
            </div>
            <ArrowRight size={16} className="quick-card-arrow" />
          </Link>

          <Link to="/my-learning" className="quick-card">
            <div className="quick-card-icon quick-icon-amber">
              <Sparkles size={20} />
            </div>
            <div className="quick-card-body">
              <h3>Genera un quiz personalizzato</h3>
              <p>
                {profile?.open_gaps.length ?? 0} lacune aperte da verificare con quiz mirati.
              </p>
            </div>
            <ArrowRight size={16} className="quick-card-arrow" />
          </Link>

          <Link to="/my-progress" className="quick-card">
            <div className="quick-card-icon quick-icon-violet">
              <TrendingUp size={20} />
            </div>
            <div className="quick-card-body">
              <h3>Analizza i tuoi progressi</h3>
              <p>Visualizza competenze acquisite, accuratezza e trend dei quiz.</p>
            </div>
            <ArrowRight size={16} className="quick-card-arrow" />
          </Link>
        </div>
      </section>

      {isLoading ? (
        <LoadingState label="Caricamento snapshot di apprendimento..." />
      ) : (
        <>
          <section aria-label="Snapshot di apprendimento">
            <h2 className="section-heading">Learning Snapshot</h2>
            <div className="stats-grid">
              <StatCard
                label="Corsi completati"
                value={`${completedCoursesCount}/${courses.length}`}
                hint={`${overview?.completed_lesson_ids.length ?? 0} lezioni completate`}
                tone="accent"
                icon={<BookOpen size={17} />}
              />
              <StatCard
                label="Quiz sostenuti"
                value={totalAttempts}
                hint={`${overview?.course_quiz_attempts.length ?? 0} tradizionali • ${
                  overview?.custom_quiz_attempts.length ?? 0
                } custom`}
                icon={<ClipboardCheck size={17} />}
              />
              <StatCard
                label="Accuratezza quiz custom"
                value={`${(metrics?.quiz_accuracy ?? 0).toFixed(1)}%`}
                hint={
                  metrics?.learning_improvement != null
                    ? `Miglioramento: ${metrics.learning_improvement > 0 ? "+" : ""}${metrics.learning_improvement.toFixed(1)}%`
                    : "Completa più verifiche per il trend"
                }
                tone="success"
                icon={<TrendingUp size={17} />}
              />
              <StatCard
                label="Lacune da verificare"
                value={profile?.open_gaps.length ?? 0}
                hint={
                  profile?.difficulty_topics.length
                    ? `Focus: ${profile.difficulty_topics.slice(0, 2).join(", ")}`
                    : "Nessuna lacuna aperta rilevata"
                }
                tone={(profile?.open_gaps.length ?? 0) > 0 ? "warning" : "default"}
                icon={<Sparkles size={17} />}
              />
            </div>
          </section>

          <section aria-label="Continua a imparare">
            <div className="section-header-row">
              <h2 className="section-heading">Continua a imparare</h2>
              <Link to="/learning" className="text-link">
                Tutti i corsi →
              </Link>
            </div>

            {inProgressOrNext.length === 0 ? (
              <div className="empty-card">
                <p>Nessun corso assegnato al momento per il tuo profilo.</p>
              </div>
            ) : (
              <div className="cards-grid">
                {inProgressOrNext.map(({ course, progress }) => (
                  <article key={course.id} className="course-card">
                    <div className="course-card-meta">
                      <StatusBadge tone="info">{formatCourseTypeLabel(course.course_type)}</StatusBadge>
                      <StatusBadge tone={progressStatusTone(progress.status)}>
                        {formatProgressStatus(progress.status)}
                      </StatusBadge>
                    </div>
                    <h3 className="course-card-title">{course.title}</h3>
                    <p className="course-card-desc">{course.description}</p>
                    <ProgressBar
                      value={progress.completion_percentage}
                      label={`${progress.completed_lessons}/${countCourseLessons(course)} lezioni`}
                    />
                    <div className="course-card-footer">
                      <span className="muted-meta">Difficoltà: {course.difficulty}</span>
                      <Link to={`/learning/${course.id}`} className="btn btn-sm btn-primary">
                        Apri corso
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
