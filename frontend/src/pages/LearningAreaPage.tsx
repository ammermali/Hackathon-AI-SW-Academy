import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BookOpen, Layers, PlusCircle, Search, Sparkles } from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  ProgressBar,
  StatusBadge,
} from "../components/common/PlatformPrimitives";
import { useAuth } from "../context/AuthContext";
import {
  generateCourse,
  getUserLearningOverview,
  listCourses,
  listOpportunities,
  listRagDocuments,
} from "../services/academyApi";
import type {
  Course,
  KnowledgeDocumentInfo,
  TrainingOpportunityItem,
  UserLearningOverview,
} from "../types/platform";
import {
  countCourseLessons,
  extractCourseSourceTags,
  formatCourseTypeLabel,
  formatLifecycleStatus,
  formatProgressStatus,
  getCourseProgressForId,
  progressStatusTone,
} from "../utils/courseHelpers";

export function LearningAreaPage() {
  const { authContext, contextVersion, isOwner, user } = useAuth();
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[]>([]);
  const [overview, setOverview] = useState<UserLearningOverview | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [lifecycleFilter, setLifecycleFilter] = useState("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Owner-only RAG course generation panel state
  const [showGeneratePanel, setShowGeneratePanel] = useState(false);
  const [ragDocs, setRagDocs] = useState<KnowledgeDocumentInfo[]>([]);
  const [opportunities, setOpportunities] = useState<TrainingOpportunityItem[]>([]);
  const [isLoadingSources, setIsLoadingSources] = useState(false);
  const [sourceMode, setSourceMode] = useState<"document" | "opportunity">("document");
  const [selectedDocSource, setSelectedDocSource] = useState("");
  const [selectedOpportunityId, setSelectedOpportunityId] = useState("");
  const [courseTypeInput, setCourseTypeInput] = useState<"documental" | "applicative">("documental");
  const [audienceScope, setAudienceScope] = useState<"all" | "owner_only">("all");
  const [isGeneratingCourse, setIsGeneratingCourse] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [coursesData, overviewData] = await Promise.all([
        listCourses(authContext),
        getUserLearningOverview(authContext, user.userId),
      ]);
      setCourses(coursesData);
      setOverview(overviewData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore nel caricamento del catalogo corsi.");
    } finally {
      setIsLoading(false);
    }
  }, [authContext, user.userId]);

  useEffect(() => {
    void loadCatalog();
  }, [contextVersion, loadCatalog]);

  useEffect(() => {
    if (!isOwner) {
      setShowGeneratePanel(false);
    }
  }, [isOwner]);

  const loadAuthoringSources = useCallback(async () => {
    if (!isOwner) return;
    setIsLoadingSources(true);
    setGenerateError(null);
    try {
      const [docsData, oppsData] = await Promise.all([
        listRagDocuments(authContext),
        listOpportunities(authContext).catch(() => []),
      ]);
      setRagDocs(docsData);
      setOpportunities(oppsData);
      if (docsData.length > 0 && !selectedDocSource) {
        setSelectedDocSource(docsData[0].source);
      }
      if (oppsData.length > 0 && !selectedOpportunityId) {
        setSelectedOpportunityId(oppsData[0].id);
      }
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "Impossibile caricare i documenti della Knowledge Base."
      );
    } finally {
      setIsLoadingSources(false);
    }
  }, [authContext, isOwner, selectedDocSource, selectedOpportunityId]);

  const handleToggleGeneratePanel = () => {
    const next = !showGeneratePanel;
    setShowGeneratePanel(next);
    if (next && ragDocs.length === 0 && !isLoadingSources) {
      void loadAuthoringSources();
    }
  };

  const handleGenerateCourse = async (e: FormEvent) => {
    e.preventDefault();
    if (!isOwner || isGeneratingCourse) return;
    setGenerateError(null);

    if (sourceMode === "document" && !selectedDocSource.trim()) {
      setGenerateError("Seleziona un documento dalla Knowledge Base.");
      return;
    }
    if (sourceMode === "opportunity" && !selectedOpportunityId.trim()) {
      setGenerateError("Seleziona una proposta formativa.");
      return;
    }

    setIsGeneratingCourse(true);
    try {
      const allowedRoles =
        audienceScope === "owner_only" ? ["owner", "admin"] : ["operatore", "owner", "admin"];
      const created = await generateCourse(authContext, {
        ...(sourceMode === "document"
          ? { document_source: selectedDocSource.trim() }
          : { opportunity_id: selectedOpportunityId.trim() }),
        course_type: courseTypeInput,
        allowed_roles: allowedRoles,
      });
      setShowGeneratePanel(false);
      navigate(`/learning/${created.id}`);
    } catch (err) {
      setGenerateError(
        err instanceof Error ? err.message : "Errore durante la generazione del corso con RAG."
      );
    } finally {
      setIsGeneratingCourse(false);
    }
  };

  const courseTypes = useMemo(
    () => Array.from(new Set(courses.map((c) => c.course_type))),
    [courses]
  );

  const filteredCourses = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return courses.filter((course) => {
      const prog = getCourseProgressForId(course, overview);
      if (typeFilter !== "ALL" && course.course_type !== typeFilter) return false;
      if (statusFilter !== "ALL" && prog.status !== statusFilter) return false;
      if (lifecycleFilter !== "ALL" && course.lifecycle_status !== lifecycleFilter) return false;
      if (!q) return true;
      const haystack = [
        course.title,
        course.description,
        course.summary,
        ...course.learning_objectives,
        ...course.modules.map((m) => m.title),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [courses, lifecycleFilter, overview, searchQuery, statusFilter, typeFilter]);

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Learning Area</h1>
          <p>
            Catalogo dei percorsi didattici generati dalla knowledge base e filtrati per il tuo
            ruolo ({user.role}).
          </p>
        </div>

        {isOwner && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleToggleGeneratePanel}
          >
            <PlusCircle size={16} aria-hidden="true" />
            <span>{showGeneratePanel ? "Chiudi generazione RAG" : "Genera corso con RAG"}</span>
          </button>
        )}
      </div>

      {isOwner && showGeneratePanel && (
        <section className="panel-card owner-authoring-panel" aria-label="Genera corso con RAG">
          <div className="panel-card-header">
            <div>
              <h2>
                <Sparkles size={18} aria-hidden="true" /> Genera nuovo corso dalla Knowledge Base
              </h2>
              <p>
                Il motore RAG + Qwen estrae procedure, esempi pratici, errori frequenti e quiz di
                verifica dal documento selezionato.
              </p>
            </div>
          </div>

          {generateError && (
            <ErrorBanner message={generateError} onRetry={() => void loadAuthoringSources()} />
          )}

          {isLoadingSources ? (
            <LoadingState label="Caricamento documenti indicizzati nella Knowledge Base..." />
          ) : (
            <form className="owner-authoring-form" onSubmit={(e) => void handleGenerateCourse(e)}>
              {opportunities.length > 0 && (
                <div className="form-field form-field-sm">
                  <label htmlFor="course-source-mode">Origine</label>
                  <select
                    id="course-source-mode"
                    value={sourceMode}
                    onChange={(e) =>
                      setSourceMode(e.target.value as "document" | "opportunity")
                    }
                  >
                    <option value="document">Documento RAG</option>
                    <option value="opportunity">Proposta formativa</option>
                  </select>
                </div>
              )}

              {sourceMode === "document" ? (
                <div className="form-field">
                  <label htmlFor="rag-doc-select">Documento Knowledge Base</label>
                  <select
                    id="rag-doc-select"
                    value={selectedDocSource}
                    onChange={(e) => setSelectedDocSource(e.target.value)}
                    required
                  >
                    {ragDocs.length === 0 ? (
                      <option value="">Nessun documento indicizzato disponibile</option>
                    ) : (
                      ragDocs.map((doc) => (
                        <option key={doc.document_id} value={doc.source}>
                          {doc.source} ({doc.chunk_count} chunk)
                        </option>
                      ))
                    )}
                  </select>
                </div>
              ) : (
                <div className="form-field">
                  <label htmlFor="rag-opp-select">Proposta formativa AI</label>
                  <select
                    id="rag-opp-select"
                    value={selectedOpportunityId}
                    onChange={(e) => setSelectedOpportunityId(e.target.value)}
                    required
                  >
                    {opportunities.map((opp) => (
                      <option key={opp.id} value={opp.id}>
                        {opp.title}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="form-field form-field-sm">
                <label htmlFor="course-type-select">Tipologia</label>
                <select
                  id="course-type-select"
                  value={courseTypeInput}
                  onChange={(e) =>
                    setCourseTypeInput(e.target.value as "documental" | "applicative")
                  }
                >
                  <option value="documental">Documentale</option>
                  <option value="applicative">Applicativo</option>
                </select>
              </div>

              <div className="form-field form-field-sm">
                <label htmlFor="course-audience-select">Destinatari</label>
                <select
                  id="course-audience-select"
                  value={audienceScope}
                  onChange={(e) => setAudienceScope(e.target.value as "all" | "owner_only")}
                >
                  <option value="all">Operatori e Owner</option>
                  <option value="owner_only">Solo Owner</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={
                  isGeneratingCourse ||
                  (sourceMode === "document" && ragDocs.length === 0) ||
                  (sourceMode === "opportunity" && opportunities.length === 0)
                }
              >
                <Sparkles size={16} aria-hidden="true" />
                <span>
                  {isGeneratingCourse ? "Generazione corso in corso..." : "Avvia generazione RAG"}
                </span>
              </button>
            </form>
          )}
        </section>
      )}

      <section className="filter-bar" aria-label="Filtri catalogo corsi">
        <div className="filter-search">
          <Search size={16} aria-hidden="true" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Cerca per titolo, obiettivo o modulo..."
            aria-label="Cerca corsi"
          />
        </div>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          aria-label="Filtra per tipologia corso"
        >
          <option value="ALL">Tutte le tipologie</option>
          {courseTypes.map((ct) => (
            <option key={ct} value={ct}>
              {formatCourseTypeLabel(ct)}
            </option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filtra per stato completamento"
        >
          <option value="ALL">Tutti gli stati personali</option>
          <option value="IN_PROGRESS">In corso</option>
          <option value="NOT_STARTED">Da iniziare</option>
          <option value="COMPLETED">Completato</option>
        </select>

        <select
          value={lifecycleFilter}
          onChange={(e) => setLifecycleFilter(e.target.value)}
          aria-label="Filtra per ciclo di vita"
        >
          <option value="ALL">Tutti gli stati pubblicazione</option>
          <option value="PUBLISHED">Pubblicati</option>
          <option value="APPROVED">Approvati</option>
          <option value="UNDER_REVIEW">In revisione</option>
          <option value="GENERATED">Generati (bozza)</option>
        </select>
      </section>

      {error && <ErrorBanner message={error} onRetry={() => void loadCatalog()} />}

      {isLoading ? (
        <LoadingState label="Caricamento corsi dal backend..." />
      ) : filteredCourses.length === 0 ? (
        <div className="empty-card">
          <BookOpen size={24} aria-hidden="true" />
          <h3>Nessun corso trovato</h3>
          <p>Prova a modificare i filtri di ricerca o genera un nuovo corso dal backend.</p>
        </div>
      ) : (
        <div className="cards-grid">
          {filteredCourses.map((course) => {
            const progress = getCourseProgressForId(course, overview);
            const totalLessons = countCourseLessons(course);
            const tags = extractCourseSourceTags(course);

            return (
              <article key={course.id} className="course-card">
                <div className="course-card-meta">
                  <StatusBadge tone="info">{formatCourseTypeLabel(course.course_type)}</StatusBadge>
                  <StatusBadge tone={progressStatusTone(progress.status)}>
                    {formatProgressStatus(progress.status)}
                  </StatusBadge>
                  <StatusBadge tone={course.lifecycle_status === "PUBLISHED" ? "success" : "warning"}>
                    {formatLifecycleStatus(course.lifecycle_status)}
                  </StatusBadge>
                </div>

                <h2 className="course-card-title">{course.title}</h2>
                <p className="course-card-desc">{course.description}</p>

                {tags.length > 0 && (
                  <div className="tag-row">
                    {tags.map((tag) => (
                      <span key={tag} className="topic-chip">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                <div className="course-card-stats">
                  <span>
                    <Layers size={14} aria-hidden="true" /> {course.modules.length} moduli •{" "}
                    {totalLessons} lezioni
                  </span>
                  <span>
                    {course.quizzes.length} {course.quizzes.length === 1 ? "quiz" : "quiz"}
                  </span>
                </div>

                <ProgressBar
                  value={progress.completion_percentage}
                  label={`${progress.completed_lessons}/${totalLessons} lezioni completate`}
                />

                <div className="course-card-footer">
                  <span className="muted-meta">
                    {progress.best_quiz_percentage != null
                      ? `Best quiz: ${progress.best_quiz_percentage.toFixed(0)}%`
                      : `Difficoltà: ${course.difficulty}`}
                  </span>
                  <Link to={`/learning/${course.id}`} className="btn btn-sm btn-primary">
                    {isOwner
                      ? "Apri e modifica"
                      : progress.status === "NOT_STARTED"
                        ? "Inizia corso"
                        : "Apri lezioni"}
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
