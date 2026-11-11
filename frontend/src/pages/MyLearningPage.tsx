import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  Play,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  ProgressBar,
  StatusBadge,
} from "../components/common/PlatformPrimitives";
import { useAuth } from "../context/AuthContext";
import { getUserLearningOverview, listCourses } from "../services/academyApi";
import {
  generateCustomQuiz,
  getCustomQuiz,
  getCustomQuizResults,
  listUserCustomQuizzes,
  submitCustomQuiz,
} from "../services/customQuizApi";
import type {
  Course,
  CustomQuiz,
  CustomQuizResult,
  UserLearningOverview,
} from "../types/platform";
import {
  countCourseLessons,
  formatItalianDate,
  formatProgressStatus,
  formatQuizSourceHint,
  getCourseProgressForId,
  progressStatusTone,
} from "../utils/courseHelpers";

type MyLearningTab = "courses" | "quizzes" | "custom";

function customOutcomeTone(outcome: string): "success" | "info" | "warning" | "danger" {
  const upper = outcome.toUpperCase();
  if (upper.includes("LEARNED") || upper.includes("COMPETENZA")) return "success";
  if (upper.includes("IMPROV") || upper.includes("PROGRESS")) return "info";
  if (upper.includes("CRITICAL") || upper.includes("FAIL")) return "danger";
  return "warning";
}

export function MyLearningPage() {
  const { authContext, contextVersion, user } = useAuth();
  const [activeTab, setActiveTab] = useState<MyLearningTab>("courses");

  const [courses, setCourses] = useState<Course[]>([]);
  const [overview, setOverview] = useState<UserLearningOverview | null>(null);
  const [customQuizzes, setCustomQuizzes] = useState<CustomQuiz[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Custom quiz generation form
  const [focusTopic, setFocusTopic] = useState("");
  const [softwareFilter, setSoftwareFilter] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);
  const [isGenerating, setIsGenerating] = useState(false);

  // Interactive Custom Quiz Runner state
  const [runnerQuiz, setRunnerQuiz] = useState<CustomQuiz | null>(null);
  const [runnerIndex, setRunnerIndex] = useState(0);
  const [runnerAnswers, setRunnerAnswers] = useState<Record<string, string>>({});
  const [runnerStartedAt, setRunnerStartedAt] = useState<number>(Date.now());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [runnerResult, setRunnerResult] = useState<CustomQuizResult | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [coursesData, overviewData, customList] = await Promise.all([
        listCourses(authContext),
        getUserLearningOverview(authContext, user.userId),
        listUserCustomQuizzes(authContext, user.userId),
      ]);
      setCourses(coursesData);
      setOverview(overviewData);
      setCustomQuizzes(customList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nel caricamento di My Learning.");
    } finally {
      setIsLoading(false);
    }
  }, [authContext, user.userId]);

  useEffect(() => {
    setRunnerQuiz(null);
    setRunnerResult(null);
    setRunnerAnswers({});
    setRunnerIndex(0);
    void loadData();
  }, [contextVersion, loadData]);

  const groupedCourses = useMemo(() => {
    const items = courses.map((course) => ({
      course,
      progress: getCourseProgressForId(course, overview),
    }));
    return {
      inProgress: items.filter((i) => i.progress.status === "IN_PROGRESS"),
      completed: items.filter((i) => i.progress.status === "COMPLETED"),
      notStarted: items.filter((i) => i.progress.status === "NOT_STARTED"),
    };
  }, [courses, overview]);

  const handleGenerateCustomQuiz = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isGenerating) return;
    setIsGenerating(true);
    setError(null);
    try {
      const generated = await generateCustomQuiz(authContext, {
        user_id: user.userId,
        num_questions: numQuestions,
        focus_topic: focusTopic.trim() || undefined,
        software: softwareFilter.trim() || undefined,
        force_new: true,
      });
      await loadData();
      setRunnerQuiz(generated);
      setRunnerIndex(0);
      setRunnerAnswers({});
      setRunnerResult(null);
      setRunnerStartedAt(Date.now());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Impossibile generare un nuovo Custom Quiz."
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleOpenQuizRunner = async (quizId: string, viewExistingResult = false) => {
    setError(null);
    try {
      const quizDetail = await getCustomQuiz(authContext, quizId);
      setRunnerQuiz(quizDetail);
      setRunnerIndex(0);
      setRunnerAnswers({});
      setRunnerStartedAt(Date.now());
      if (viewExistingResult) {
        const res = await getCustomQuizResults(authContext, quizId, user.userId);
        setRunnerResult(res);
      } else {
        setRunnerResult(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile aprire il Custom Quiz.");
    }
  };

  const handleSubmitRunner = async () => {
    if (!runnerQuiz || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const elapsedSeconds = Math.max(1, Math.round((Date.now() - runnerStartedAt) / 1000));
      const result = await submitCustomQuiz(authContext, runnerQuiz.id, {
        user_id: user.userId,
        answers: runnerAnswers,
        duration_seconds: elapsedSeconds,
      });
      setRunnerResult(result);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nell'invio del Custom Quiz.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentQuestion = runnerQuiz?.questions[runnerIndex] ?? null;
  const totalRunnerQuestions = runnerQuiz?.questions.length ?? 0;
  const allRunnerAnswered =
    totalRunnerQuestions > 0 &&
    runnerQuiz!.questions.every((q) => Boolean(runnerAnswers[q.id]));

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>My Learning</h1>
          <p>
            Gestisci i tuoi corsi, consulta lo storico dei quiz didattici e genera Custom Quiz
            adattivi sulle tue lacune.
          </p>
        </div>
      </div>

      <div className="tabs-row" role="tablist" aria-label="Sezioni My Learning">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "courses"}
          className={`tab-btn ${activeTab === "courses" ? "is-active" : ""}`}
          onClick={() => setActiveTab("courses")}
        >
          <BookOpen size={15} />
          <span>My Courses ({courses.length})</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "quizzes"}
          className={`tab-btn ${activeTab === "quizzes" ? "is-active" : ""}`}
          onClick={() => setActiveTab("quizzes")}
        >
          <ClipboardCheck size={15} />
          <span>My Quizzes ({overview?.course_quiz_attempts.length ?? 0})</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "custom"}
          className={`tab-btn ${activeTab === "custom" ? "is-active" : ""}`}
          onClick={() => setActiveTab("custom")}
        >
          <Sparkles size={15} />
          <span>My Custom Quizzes ({customQuizzes.length})</span>
        </button>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => void loadData()} />}

      {isLoading ? (
        <LoadingState label="Caricamento dati personali..." />
      ) : activeTab === "courses" ? (
        <div className="stack-lg">
          {(
            [
              { title: "In corso", items: groupedCourses.inProgress },
              { title: "Completati", items: groupedCourses.completed },
              { title: "Da iniziare", items: groupedCourses.notStarted },
            ] as const
          ).map((group) => (
            <section key={group.title} className="stack-sm">
              <h2 className="section-heading">
                {group.title} ({group.items.length})
              </h2>
              {group.items.length === 0 ? (
                <p className="muted-meta">Nessun corso in questa categoria.</p>
              ) : (
                <div className="cards-grid">
                  {group.items.map(({ course, progress }) => (
                    <article key={course.id} className="course-card">
                      <div className="course-card-meta">
                        <StatusBadge tone={progressStatusTone(progress.status)}>
                          {formatProgressStatus(progress.status)}
                        </StatusBadge>
                        {progress.best_quiz_percentage != null && (
                          <StatusBadge tone="neutral">
                            Best quiz: {progress.best_quiz_percentage.toFixed(0)}%
                          </StatusBadge>
                        )}
                      </div>
                      <h3 className="course-card-title">{course.title}</h3>
                      <ProgressBar
                        value={progress.completion_percentage}
                        label={`${progress.completed_lessons}/${countCourseLessons(course)} lezioni`}
                      />
                      <div className="course-card-footer">
                        <span className="muted-meta">
                          Ultima attività: {formatItalianDate(progress.last_activity_at)}
                        </span>
                        <Link to={`/learning/${course.id}`} className="btn btn-sm btn-primary">
                          Apri corso
                        </Link>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      ) : activeTab === "quizzes" ? (
        <section className="panel-card">
          <h2 className="section-heading">Storico Quiz Tradizionali</h2>
          {(overview?.course_quiz_attempts.length ?? 0) === 0 ? (
            <div className="empty-card">
              <p>Non hai ancora completato quiz didattici nei corsi.</p>
              <Link to="/learning" className="btn btn-primary btn-sm">
                Vai al Learning Area
              </Link>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Corso</th>
                    <th>Quiz</th>
                    <th>Esito</th>
                    <th>Punteggio</th>
                    <th>Argomenti errati</th>
                    <th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {overview!.course_quiz_attempts.map((attempt) => (
                    <tr key={attempt.attempt_id}>
                      <td>
                        <Link to={`/learning/${attempt.course_id}`} className="text-link">
                          {attempt.course_title}
                        </Link>
                      </td>
                      <td>{attempt.quiz_title}</td>
                      <td>
                        <StatusBadge tone={attempt.passed ? "success" : "warning"}>
                          {attempt.passed ? "Superato" : "Da consolidare"}
                        </StatusBadge>
                      </td>
                      <td>
                        <strong>{attempt.percentage.toFixed(1)}%</strong>
                      </td>
                      <td>
                        {attempt.wrong_topics.length > 0
                          ? attempt.wrong_topics.join(", ")
                          : "Nessuno"}
                      </td>
                      <td>{formatItalianDate(attempt.completed_at, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : (
        <div className="stack-lg">
          {runnerQuiz && (
            <section className="panel-card custom-quiz-runner-card" aria-label="Custom Quiz Runner">
              <div className="runner-header">
                <div>
                  <StatusBadge tone="info">Custom Quiz Adattivo</StatusBadge>
                  <h2>
                    {runnerQuiz.software} • {runnerQuiz.module_name}
                  </h2>
                  <p className="muted-meta">
                    Argomenti verificati: {runnerQuiz.topics_verified.join(", ") || "Generale"}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setRunnerQuiz(null);
                    setRunnerResult(null);
                  }}
                >
                  Chiudi runner
                </button>
              </div>

              {runnerResult ? (
                <div className="stack-md">
                  <div className="quiz-result-box">
                    <StatusBadge tone={customOutcomeTone(runnerResult.outcome)}>
                      {runnerResult.outcome}
                    </StatusBadge>
                    <h3>
                      Risultato: {runnerResult.percentage.toFixed(1)}% ({runnerResult.correct_count}/
                      {runnerResult.total_questions} corrette)
                    </h3>
                    <p className="muted-meta">
                      Tempo impiegato: {runnerResult.duration_seconds}s • Completato:{" "}
                      {formatItalianDate(runnerResult.completed_at, true)}
                    </p>
                  </div>

                  {runnerResult.recommended_lessons.length > 0 && (
                    <div className="recommended-box">
                      <h3>Lezioni consigliate per il recupero</h3>
                      <div className="recommended-list">
                        {runnerResult.recommended_lessons.map((rec, idx) => (
                          <div key={idx} className="recommended-item">
                            <div>
                              <strong>{rec.lesson_title ?? rec.course_title}</strong>
                              <div className="muted-meta">
                                Topic: {rec.topic} • {rec.reason}
                              </div>
                            </div>
                            <Link
                              to={`/learning/${rec.course_id}`}
                              className="btn btn-sm btn-primary"
                            >
                              Studia lezione
                            </Link>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="stack-sm">
                    <h3>Dettaglio risposte</h3>
                    {runnerResult.question_feedback.map((fb, idx) => (
                      <div
                        key={fb.question_id}
                        className={`feedback-item ${fb.is_correct ? "is-correct" : "is-wrong"}`}
                      >
                        <div className="feedback-head">
                          <span className="feedback-title">
                            {fb.is_correct ? (
                              <CheckCircle2 size={16} className="text-success" />
                            ) : (
                              <XCircle size={16} className="text-danger" />
                            )}
                            Domanda {idx + 1} • {fb.topic}
                          </span>
                          <StatusBadge tone={fb.is_correct ? "success" : "danger"}>
                            {fb.is_correct ? "Corretta" : `Risposta esatta: ${fb.correct_option_id}`}
                          </StatusBadge>
                        </div>
                        <p>{fb.explanation}</p>
                        {!fb.is_correct && (
                          <p className="muted-meta">Soluzione attesa: {fb.correct_answer}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : currentQuestion ? (
                <div className="stack-md">
                  <div className="runner-progress-row">
                    <span>
                      Domanda {runnerIndex + 1} di {totalRunnerQuestions}
                    </span>
                    <StatusBadge tone="neutral">{currentQuestion.topic}</StatusBadge>
                  </div>
                  <ProgressBar value={((runnerIndex + 1) / totalRunnerQuestions) * 100} />

                  <div className="quiz-question-card">
                    <p className="quiz-question-text">{currentQuestion.question_text}</p>
                    {currentQuestion.sources?.[0] && (() => {
                      const src = currentQuestion.sources[0];
                      const hint = formatQuizSourceHint(
                        typeof src.document === "string" ? src.document : null,
                        typeof src.section === "string" ? src.section : null
                      );
                      return hint ? <div className="quiz-source-hint">Fonte: {hint}</div> : null;
                    })()}
                    <div className="quiz-options-list">
                      {currentQuestion.options.map((opt) => {
                        const selected = runnerAnswers[currentQuestion.id] === opt.id;
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            className={`quiz-option-btn ${selected ? "is-selected" : ""}`}
                            onClick={() =>
                              setRunnerAnswers((prev) => ({
                                ...prev,
                                [currentQuestion.id]: opt.id,
                              }))
                            }
                          >
                            <strong>{opt.id}.</strong> {opt.text}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="runner-nav-row">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={runnerIndex === 0}
                      onClick={() => setRunnerIndex((i) => Math.max(0, i - 1))}
                    >
                      <ArrowLeft size={15} /> Precedente
                    </button>

                    {runnerIndex < totalRunnerQuestions - 1 ? (
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={!runnerAnswers[currentQuestion.id]}
                        onClick={() =>
                          setRunnerIndex((i) => Math.min(totalRunnerQuestions - 1, i + 1))
                        }
                      >
                        Successiva <ArrowRight size={15} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={!allRunnerAnswered || isSubmitting}
                        onClick={() => void handleSubmitRunner()}
                      >
                        {isSubmitting ? "Valutazione..." : "Completa e valuta"}
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <p>Nessuna domanda disponibile per questo Custom Quiz.</p>
              )}
            </section>
          )}

          <section className="panel-card">
            <h2 className="section-heading">Genera un nuovo Custom Quiz (Qwen)</h2>
            <form className="generate-quiz-form" onSubmit={(e) => void handleGenerateCustomQuiz(e)}>
              <div className="form-field">
                <label htmlFor="custom-topic-input">Argomento focus (opzionale)</label>
                <input
                  id="custom-topic-input"
                  type="text"
                  value={focusTopic}
                  onChange={(e) => setFocusTopic(e.target.value)}
                  placeholder="Es. rimozione verbale da ruolo"
                />
              </div>

              <div className="form-field">
                <label htmlFor="custom-software-input">Software (opzionale)</label>
                <input
                  id="custom-software-input"
                  type="text"
                  value={softwareFilter}
                  onChange={(e) => setSoftwareFilter(e.target.value)}
                  placeholder="Es. Verbali CDS"
                />
              </div>

              <div className="form-field form-field-sm">
                <label htmlFor="custom-count-select">Domande</label>
                <select
                  id="custom-count-select"
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(Number(e.target.value))}
                >
                  <option value={3}>3 domande</option>
                  <option value={5}>5 domande</option>
                  <option value={7}>7 domande</option>
                </select>
              </div>

              <button type="submit" className="btn btn-primary" disabled={isGenerating}>
                {isGenerating ? (
                  <>
                    <Loader2 size={16} className="spin" aria-hidden="true" />
                    <span>Generazione Qwen...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={16} aria-hidden="true" />
                    <span>Genera Custom Quiz</span>
                  </>
                )}
              </button>
            </form>
          </section>

          <section className="panel-card">
            <h2 className="section-heading">I tuoi Custom Quiz</h2>
            {customQuizzes.length === 0 ? (
              <div className="empty-card">
                <p>
                  Nessun Custom Quiz ancora generato. Usa il modulo qui sopra per creare un quiz
                  personalizzato in base alle tue domande RAG e alle tue lacune.
                </p>
              </div>
            ) : (
              <div className="cards-grid">
                {customQuizzes.map((cq) => {
                  const isDone = cq.status === "COMPLETED";
                  return (
                    <article key={cq.id} className="course-card">
                      <div className="course-card-meta">
                        <StatusBadge tone={isDone ? "success" : "info"}>{cq.status}</StatusBadge>
                        <StatusBadge tone="neutral">{cq.num_questions} domande</StatusBadge>
                      </div>
                      <h3 className="course-card-title">
                        {cq.software} • {cq.module_name}
                      </h3>
                      <p className="course-card-desc">
                        Argomenti: {cq.topics_verified.join(", ") || "Ripasso generale"}
                      </p>
                      <div className="course-card-footer">
                        <span className="muted-meta">{formatItalianDate(cq.generated_at, true)}</span>
                        <button
                          type="button"
                          className={`btn btn-sm ${isDone ? "btn-secondary" : "btn-primary"}`}
                          onClick={() => void handleOpenQuizRunner(cq.id, isDone)}
                        >
                          <Play size={14} aria-hidden="true" />
                          <span>{isDone ? "Vedi risultato" : "Svolgi quiz"}</span>
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
