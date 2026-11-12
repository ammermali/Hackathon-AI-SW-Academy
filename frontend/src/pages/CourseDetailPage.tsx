import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  GraduationCap,
  XCircle,
} from "lucide-react";
import { MarkdownRenderer } from "../components/MarkdownRenderer";
import {
  OwnerCourseAuthoringBar,
  OwnerLessonEditor,
} from "../components/academy/OwnerCourseAuthoring";
import {
  ErrorBanner,
  LoadingState,
  ProgressBar,
  StatusBadge,
} from "../components/common/PlatformPrimitives";
import { useAuth } from "../context/AuthContext";
import {
  completeLesson,
  getCourse,
  getUserLearningOverview,
  submitCourseQuiz,
} from "../services/academyApi";
import type {
  Course,
  CourseQuiz,
  CourseQuizSubmitResponse,
  Lesson,
  UserLearningOverview,
} from "../types/platform";
import {
  formatCourseTypeLabel,
  formatLifecycleStatus,
  formatQuizSourceHint,
  getCourseProgressForId,
} from "../utils/courseHelpers";

interface FlatLessonRef {
  moduleTitle: string;
  lesson: Lesson;
}

export function CourseDetailPage() {
  const { courseId = "" } = useParams<{ courseId: string }>();
  const { authContext, contextVersion, isOwner, user } = useAuth();

  const [course, setCourse] = useState<Course | null>(null);
  const [overview, setOverview] = useState<UserLearningOverview | null>(null);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<CourseQuiz | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizResult, setQuizResult] = useState<CourseQuizSubmitResponse | null>(null);
  const [isSubmittingQuiz, setIsSubmittingQuiz] = useState(false);
  const [isCompletingLesson, setIsCompletingLesson] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authoringFeedback, setAuthoringFeedback] = useState<string | null>(null);

  const loadCourseDetail = useCallback(async () => {
    if (!courseId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [courseData, overviewData] = await Promise.all([
        getCourse(authContext, courseId),
        getUserLearningOverview(authContext, user.userId),
      ]);
      setCourse(courseData);
      setOverview(overviewData);
      const firstLesson = courseData.modules[0]?.lessons[0] ?? null;
      setSelectedLessonId((prev) => prev ?? firstLesson?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nel caricamento del corso.");
    } finally {
      setIsLoading(false);
    }
  }, [authContext, courseId, user.userId]);

  useEffect(() => {
    setSelectedLessonId(null);
    setActiveQuiz(null);
    setQuizResult(null);
    setQuizAnswers({});
    void loadCourseDetail();
  }, [contextVersion, loadCourseDetail]);

  const flatLessons = useMemo<FlatLessonRef[]>(() => {
    if (!course) return [];
    const list: FlatLessonRef[] = [];
    const sortedModules = [...course.modules].sort((a, b) => a.order_index - b.order_index);
    for (const mod of sortedModules) {
      const sortedLessons = [...mod.lessons].sort((a, b) => a.order_index - b.order_index);
      for (const lesson of sortedLessons) {
        list.push({ moduleTitle: mod.title, lesson });
      }
    }
    return list;
  }, [course]);

  const currentIdx = flatLessons.findIndex((item) => item.lesson.id === selectedLessonId);
  const currentRef = currentIdx >= 0 ? flatLessons[currentIdx] : flatLessons[0] ?? null;
  const completedSet = useMemo(
    () => new Set(overview?.completed_lesson_ids ?? []),
    [overview]
  );

  const handleMarkLessonComplete = async () => {
    if (!course || !currentRef || isCompletingLesson) return;
    setIsCompletingLesson(true);
    try {
      await completeLesson(authContext, course.id, currentRef.lesson.id);
      const refreshed = await getUserLearningOverview(authContext, user.userId);
      setOverview(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile registrare il completamento.");
    } finally {
      setIsCompletingLesson(false);
    }
  };

  const handleOpenQuiz = (quiz: CourseQuiz) => {
    setActiveQuiz(quiz);
    setQuizAnswers({});
    setQuizResult(null);
  };

  const handleSubmitCourseQuiz = async () => {
    if (!course || !activeQuiz || isSubmittingQuiz) return;
    setIsSubmittingQuiz(true);
    setError(null);
    try {
      const result = await submitCourseQuiz(authContext, course.id, activeQuiz.id, quizAnswers);
      setQuizResult(result);
      const refreshed = await getUserLearningOverview(authContext, user.userId);
      setOverview(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore durante la valutazione del quiz.");
    } finally {
      setIsSubmittingQuiz(false);
    }
  };

  if (isLoading) {
    return (
      <div className="page-container">
        <LoadingState label="Caricamento corso e lezioni..." />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="page-container">
        <Link to="/learning" className="back-link">
          <ArrowLeft size={15} /> Torna all&apos;Area Formazione
        </Link>
        <ErrorBanner message={error ?? "Corso non trovato."} onRetry={() => void loadCourseDetail()} />
      </div>
    );
  }

  const courseProgress = getCourseProgressForId(course, overview);
  const isCurrentLessonCompleted = currentRef ? completedSet.has(currentRef.lesson.id) : false;

  return (
    <div className="page-container">
      <div className="breadcrumb-row">
        <Link to="/learning" className="back-link">
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Torna al catalogo corsi</span>
        </Link>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => void loadCourseDetail()} />}
      {authoringFeedback && (
        <div className="authoring-feedback-banner" role="status">
          <CheckCircle2 size={16} aria-hidden="true" />
          <span>{authoringFeedback}</span>
        </div>
      )}

      {isOwner && (
        <OwnerCourseAuthoringBar
          authContext={authContext}
          course={course}
          onError={(msg) => {
            setAuthoringFeedback(null);
            setError(msg);
          }}
          onCourseUpdated={(updated, msg) => {
            setError(null);
            setAuthoringFeedback(msg ?? null);
            if (msg?.includes("Ricaricamento")) {
              void loadCourseDetail();
            } else {
              setCourse(updated);
            }
          }}
        />
      )}

      <section className="course-hero-card">
        <div className="course-hero-main">
          <div className="course-card-meta">
            <StatusBadge tone="info">{formatCourseTypeLabel(course.course_type)}</StatusBadge>
            <StatusBadge tone={course.lifecycle_status === "PUBLISHED" ? "success" : "warning"}>
              {formatLifecycleStatus(course.lifecycle_status)}
            </StatusBadge>
            <StatusBadge tone="neutral">Difficoltà: {course.difficulty}</StatusBadge>
          </div>
          <h1>{course.title}</h1>
          <p className="course-hero-desc">{course.description}</p>
          {course.learning_objectives.length > 0 && (
            <div className="objectives-list">
              <strong>Obiettivi formativi:</strong>
              <ul>
                {course.learning_objectives.map((obj, idx) => (
                  <li key={idx}>{obj}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="course-hero-progress">
          <ProgressBar
            value={courseProgress.completion_percentage}
            label={`Avanzamento (${courseProgress.completed_lessons}/${courseProgress.total_lessons} lezioni)`}
          />
          {courseProgress.best_quiz_percentage != null && (
            <div className="muted-meta">
              Miglior punteggio quiz: <strong>{courseProgress.best_quiz_percentage.toFixed(1)}%</strong>
            </div>
          )}
        </div>
      </section>

      <div className="course-workspace-grid">
        <aside className="course-outline-panel" aria-label="Struttura del corso">
          <h2>Moduli e Lezioni</h2>
          {course.modules
            .slice()
            .sort((a, b) => a.order_index - b.order_index)
            .map((mod) => (
              <div key={mod.id} className="outline-module">
                <div className="outline-module-title">{mod.title}</div>
                <ul className="outline-lesson-list">
                  {mod.lessons
                    .slice()
                    .sort((a, b) => a.order_index - b.order_index)
                    .map((lesson) => {
                      const done = completedSet.has(lesson.id);
                      const isActive = !activeQuiz && currentRef?.lesson.id === lesson.id;
                      return (
                        <li key={lesson.id}>
                          <button
                            type="button"
                            className={`outline-lesson-btn ${isActive ? "is-active" : ""}`}
                            onClick={() => {
                              setActiveQuiz(null);
                              setSelectedLessonId(lesson.id);
                            }}
                          >
                            <span className="outline-lesson-status">
                              {done ? (
                                <CheckCircle2 size={15} className="text-success" />
                              ) : (
                                <GraduationCap size={15} />
                              )}
                            </span>
                            <span>{lesson.title}</span>
                          </button>
                        </li>
                      );
                    })}
                </ul>
              </div>
            ))}

          {course.quizzes.length > 0 && (
            <div className="outline-module">
              <div className="outline-module-title">Quiz di verifica</div>
              <ul className="outline-lesson-list">
                {course.quizzes.map((quiz) => (
                  <li key={quiz.id}>
                    <button
                      type="button"
                      className={`outline-lesson-btn ${activeQuiz?.id === quiz.id ? "is-active" : ""}`}
                      onClick={() => handleOpenQuiz(quiz)}
                    >
                      <ClipboardCheck size={15} />
                      <span>
                        {quiz.title} ({quiz.questions.length} domande)
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>

        <section className="lesson-viewer-panel">
          {activeQuiz ? (
            <div className="quiz-panel">
              <div className="lesson-viewer-header">
                <div>
                  <div className="lesson-module-kicker">Quiz didattico del corso</div>
                  <h2>{activeQuiz.title}</h2>
                  <p className="muted-meta">
                    Soglia superamento: {activeQuiz.passing_score.toFixed(0)}% •{" "}
                    {activeQuiz.questions.length} domande
                  </p>
                </div>
              </div>

              {quizResult ? (
                <div className="quiz-result-box">
                  <StatusBadge tone={quizResult.passed ? "success" : "warning"}>
                    {quizResult.passed ? "Quiz superato" : "Da consolidare"}
                  </StatusBadge>
                  <h3>
                    Punteggio: {quizResult.percentage.toFixed(1)}% ({quizResult.correct_count}/
                    {quizResult.total_questions} corrette)
                  </h3>
                  {quizResult.wrong_topics.length > 0 && (
                    <p>
                      Argomenti da ripassare: <strong>{quizResult.wrong_topics.join(", ")}</strong>
                    </p>
                  )}
                  {quizResult.question_feedback && quizResult.question_feedback.length > 0 && (
                    <div className="stack-sm">
                      <h4>Dettaglio risposte</h4>
                      {quizResult.question_feedback.map((fb, idx) => (
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
                              Domanda {idx + 1}
                            </span>
                            <StatusBadge tone={fb.is_correct ? "success" : "danger"}>
                              {fb.is_correct ? "Corretta" : "Errata"}
                            </StatusBadge>
                          </div>
                          <p><strong>{fb.question_text}</strong></p>
                          <p className="muted-meta">La tua risposta: {fb.user_answer || "—"}</p>
                          {!fb.is_correct && (
                            <p className="muted-meta">
                              <strong>Risposta corretta:</strong> {fb.correct_answer}
                            </p>
                          )}
                          {fb.explanation && <p>{fb.explanation}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="quiz-result-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setQuizAnswers({});
                        setQuizResult(null);
                      }}
                    >
                      Ripeti quiz
                    </button>
                    <Link to="/my-learning" className="btn btn-primary">
                      Vai a La mia formazione
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="quiz-questions-stack">
                  {activeQuiz.questions
                    .slice()
                    .sort((a, b) => a.order_index - b.order_index)
                    .map((q, idx) => (
                      <div key={q.id} className="quiz-question-card">
                        <div className="quiz-question-num">
                          Domanda {idx + 1} di {activeQuiz.questions.length}
                        </div>
                        <p className="quiz-question-text">{q.question_text}</p>
                        {formatQuizSourceHint(null, q.source_section) && (
                          <div className="quiz-source-hint">
                            Fonte: {formatQuizSourceHint(null, q.source_section)}
                          </div>
                        )}
                        <div className="quiz-options-list">
                          {q.options.map((opt) => {
                            const selected = quizAnswers[q.id] === opt;
                            return (
                              <button
                                key={opt}
                                type="button"
                                className={`quiz-option-btn ${selected ? "is-selected" : ""}`}
                                onClick={() =>
                                  setQuizAnswers((prev) => ({ ...prev, [q.id]: opt }))
                                }
                              >
                                {opt}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}

                  <div className="quiz-submit-row">
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={
                        isSubmittingQuiz ||
                        Object.keys(quizAnswers).length < activeQuiz.questions.length
                      }
                      onClick={() => void handleSubmitCourseQuiz()}
                    >
                      {isSubmittingQuiz ? "Valutazione in corso..." : "Invia risposte quiz"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : currentRef ? (
            <article className="lesson-article">
              <div className="lesson-viewer-header">
                <div>
                  <div className="lesson-module-kicker">{currentRef.moduleTitle}</div>
                  <h2>{currentRef.lesson.title}</h2>
                  {currentRef.lesson.objective && (
                    <p className="lesson-objective">Obiettivo: {currentRef.lesson.objective}</p>
                  )}
                </div>

                {isCurrentLessonCompleted && (
                  <StatusBadge tone="success">Lezione completata</StatusBadge>
                )}
              </div>

              {!currentRef.lesson.is_grounded && currentRef.lesson.grounding_warnings.length > 0 && (
                <div className="grounding-alert">
                  <AlertTriangle size={16} />
                  <span>{currentRef.lesson.grounding_warnings.join(" • ")}</span>
                </div>
              )}

              {isOwner && (
                <OwnerLessonEditor
                  authContext={authContext}
                  courseId={course.id}
                  lesson={currentRef.lesson}
                  onError={(msg) => {
                    setAuthoringFeedback(null);
                    setError(msg);
                  }}
                  onLessonUpdated={(_updatedLesson, msg) => {
                    setError(null);
                    setAuthoringFeedback(msg);
                    void loadCourseDetail();
                  }}
                />
              )}

              <div className="lesson-section">
                <MarkdownRenderer content={currentRef.lesson.explanation} />
              </div>

              {currentRef.lesson.procedures.length > 0 && (
                <div className="lesson-section">
                  <h3>Procedure operative</h3>
                  <ol className="lesson-steps-list">
                    {currentRef.lesson.procedures.map((step, i) => (
                      <li key={i} className="lesson-step-markdown">
                        <MarkdownRenderer content={step} />
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {currentRef.lesson.practical_examples.length > 0 && (
                <div className="lesson-section">
                  <h3>Esempi pratici</h3>
                  <div className="lesson-cards-stack">
                    {currentRef.lesson.practical_examples.map((ex, i) => {
                      const title = String(ex.label ?? ex.scenario ?? "").trim();
                      const bodyMarkdown = typeof ex.content === "string" ? ex.content.trim() : "";
                      const legacySteps = Array.isArray(ex.steps) ? ex.steps : [];
                      const legacyResult = ex.expected_result ? String(ex.expected_result) : "";
                      const hasContent = Boolean(title || bodyMarkdown || legacySteps.length || legacyResult);
                      if (!hasContent) return null;

                      return (
                        <div key={i} className="lesson-subcard">
                          <div className="lesson-subcard-head">
                            {title && <h4>{title}</h4>}
                            {typeof ex.is_correct === "boolean" && (
                              <StatusBadge tone={ex.is_correct ? "success" : "danger"}>
                                {ex.is_correct ? "Esempio corretto" : "Esempio da evitare"}
                              </StatusBadge>
                            )}
                          </div>
                          {bodyMarkdown && (
                            <div className="lesson-step-markdown">
                              <MarkdownRenderer content={bodyMarkdown} />
                            </div>
                          )}
                          {legacySteps.length > 0 && (
                            <ul>
                              {legacySteps.map((s, si) => (
                                <li key={si} className="lesson-step-markdown">
                                  <MarkdownRenderer content={String(s)} />
                                </li>
                              ))}
                            </ul>
                          )}
                          {legacyResult && (
                            <p className="muted-meta">
                              <strong>Risultato atteso:</strong> {legacyResult}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {currentRef.lesson.frequent_errors.length > 0 && (
                <div className="lesson-section">
                  <h3>Errori frequenti e soluzioni</h3>
                  <div className="lesson-cards-stack">
                    {currentRef.lesson.frequent_errors.map((fe, i) => {
                      const errTitle = String(fe.error_or_antipattern ?? fe.error ?? "").trim();
                      const errFix = String(fe.consequence_or_fix ?? fe.solution ?? "").trim();
                      const errCause = fe.cause ? String(fe.cause).trim() : "";
                      if (!errTitle && !errFix && !errCause) return null;

                      return (
                        <div key={i} className="lesson-subcard lesson-subcard-warn">
                          {errTitle && (
                            <div className="lesson-step-markdown">
                              <strong>Errore / Antipattern:</strong>
                              <MarkdownRenderer content={errTitle} />
                            </div>
                          )}
                          {errCause && (
                            <p>
                              <strong>Causa:</strong> {errCause}
                            </p>
                          )}
                          {errFix && (
                            <div className="lesson-step-markdown">
                              <strong>Indicazione correttiva:</strong>
                              <MarkdownRenderer content={errFix} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {currentRef.lesson.exercises.length > 0 && (
                <div className="lesson-section">
                  <h3>Esercitazioni</h3>
                  <div className="lesson-cards-stack">
                    {currentRef.lesson.exercises.map((ex, i) => {
                      const exTitle = String(ex.title ?? "").trim();
                      const exScenario = String(ex.scenario ?? ex.instruction ?? "").trim();
                      const expectedSteps = Array.isArray(ex.expected_steps) ? ex.expected_steps : [];
                      const expectedOutcome = ex.expected_outcome ? String(ex.expected_outcome).trim() : "";
                      if (!exTitle && !exScenario && expectedSteps.length === 0 && !expectedOutcome) {
                        return null;
                      }

                      return (
                        <div key={i} className="lesson-subcard">
                          {exTitle && <h4>{exTitle}</h4>}
                          {exScenario && <p>{exScenario}</p>}
                          {expectedSteps.length > 0 && (
                            <ol className="lesson-steps-list">
                              {expectedSteps.map((step, si) => (
                                <li key={si} className="lesson-step-markdown">
                                  <MarkdownRenderer content={String(step)} />
                                </li>
                              ))}
                            </ol>
                          )}
                          {expectedOutcome && (
                            <p className="muted-meta">
                              <strong>Verifica:</strong> {expectedOutcome}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {currentRef.lesson.summary && (
                <div className="lesson-summary-box">
                  <h3>Sintesi</h3>
                  <div className="lesson-step-markdown">
                    <MarkdownRenderer content={currentRef.lesson.summary} />
                  </div>
                </div>
              )}

              {currentRef.lesson.sources.length > 0 && (
                <div className="lesson-section">
                  <h3>Fonti documentali citate</h3>
                  <div className="sources-list">
                    {currentRef.lesson.sources.map((src, idx) => (
                      <div key={`${src.chunk_id}-${idx}`} className="source-item">
                        <div className="source-item-head">
                          <span className="source-title">
                            <FileText size={14} aria-hidden="true" /> {src.document_title}
                          </span>
                          <span className="source-section-tag">
                            {src.section || "Manuale"}
                            {src.page != null ? ` • p. ${src.page}` : ""}
                          </span>
                        </div>
                        {src.excerpt && <p className="source-excerpt">{src.excerpt}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="lesson-nav-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={currentIdx <= 0}
                  onClick={() => {
                    const prev = flatLessons[currentIdx - 1];
                    if (prev) setSelectedLessonId(prev.lesson.id);
                  }}
                >
                  <ArrowLeft size={15} /> Lezione precedente
                </button>

                <button
                  type="button"
                  className={`btn ${isCurrentLessonCompleted ? "btn-success-outline" : "btn-primary"}`}
                  disabled={isCompletingLesson || isCurrentLessonCompleted}
                  onClick={() => void handleMarkLessonComplete()}
                >
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <span>
                    {isCurrentLessonCompleted
                      ? "Lezione completata"
                      : isCompletingLesson
                        ? "Salvataggio..."
                        : "Segna lezione come completata"}
                  </span>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={currentIdx >= flatLessons.length - 1}
                  onClick={() => {
                    const next = flatLessons[currentIdx + 1];
                    if (next) setSelectedLessonId(next.lesson.id);
                  }}
                >
                  Lezione successiva <ArrowRight size={15} />
                </button>
              </div>
            </article>
          ) : (
            <div className="empty-card">
              <p>Questo corso non contiene ancora lezioni.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
