import { useEffect, useState, type FormEvent } from "react";
import { Pencil, RefreshCw, Save, Send, Sparkles, X } from "lucide-react";
import {
  generateCourseQuiz,
  regenerateLesson,
  transitionCourseLifecycle,
  updateCourse,
  updateLesson,
} from "../../services/academyApi";
import type { Course, Lesson, RequestAuthContext } from "../../types/platform";
import { StatusBadge } from "../common/PlatformPrimitives";

interface OwnerCourseAuthoringBarProps {
  authContext: RequestAuthContext;
  course: Course;
  onCourseUpdated: (updated: Course, message?: string) => void;
  onError: (message: string) => void;
}

export function OwnerCourseAuthoringBar({
  authContext,
  course,
  onCourseUpdated,
  onError,
}: OwnerCourseAuthoringBarProps) {
  const [isEditingCourse, setIsEditingCourse] = useState(false);
  const [title, setTitle] = useState(course.title);
  const [description, setDescription] = useState(course.description);
  const [summary, setSummary] = useState(course.summary);
  const [difficulty, setDifficulty] = useState(course.difficulty);
  const [changeSummary, setChangeSummary] = useState("Aggiornamento manuale Owner");
  const [busyAction, setBusyAction] = useState<string | null>(null);

  useEffect(() => {
    setTitle(course.title);
    setDescription(course.description);
    setSummary(course.summary);
    setDifficulty(course.difficulty);
  }, [course]);

  const handleSaveCourse = async (e: FormEvent) => {
    e.preventDefault();
    if (busyAction) return;
    setBusyAction("save-course");
    try {
      const updated = await updateCourse(authContext, course.id, {
        title: title.trim(),
        description: description.trim(),
        summary: summary.trim(),
        difficulty,
        change_summary: changeSummary.trim() || "Aggiornamento manuale Owner",
      });
      setIsEditingCourse(false);
      onCourseUpdated(updated, "Metadati del corso aggiornati e nuova revisione salvata.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Errore durante il salvataggio del corso.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleTransition = async (
    targetStatus: "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "PUBLISHED",
    label: string
  ) => {
    if (busyAction) return;
    setBusyAction(targetStatus);
    try {
      const updated = await transitionCourseLifecycle(
        authContext,
        course.id,
        targetStatus,
        `Azione Owner da UI: ${label}`
      );
      onCourseUpdated(updated, `Stato del corso aggiornato a ${updated.lifecycle_status}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Impossibile cambiare lo stato del corso.");
    } finally {
      setBusyAction(null);
    }
  };

  const handleRegenerateQuiz = async () => {
    if (busyAction) return;
    setBusyAction("quiz");
    try {
      await generateCourseQuiz(authContext, course.id, { numQuestions: 5 });
      onCourseUpdated(course, "Nuovo quiz generato con RAG. Ricaricamento corso...",);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Errore nella rigenerazione del quiz.");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <section className="panel-card owner-authoring-bar" aria-label="Strumenti Owner gestione corso">
      <div className="owner-authoring-bar-row">
        <div className="owner-authoring-bar-info">
          <StatusBadge tone="info">Gestione Owner • v{course.current_version}</StatusBadge>
          <span className="muted-meta">
            Puoi modificare titolo, lezioni, rigenerare contenuti con RAG o gestire la pubblicazione.
          </span>
        </div>

        <div className="owner-authoring-actions">
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            disabled={Boolean(busyAction)}
            onClick={() => setIsEditingCourse((prev) => !prev)}
          >
            <Pencil size={14} aria-hidden="true" />
            <span>{isEditingCourse ? "Annulla modifica corso" : "Modifica corso"}</span>
          </button>

          <button
            type="button"
            className="btn btn-sm btn-secondary"
            disabled={Boolean(busyAction)}
            onClick={() => void handleRegenerateQuiz()}
          >
            <Sparkles size={14} aria-hidden="true" />
            <span>{busyAction === "quiz" ? "Generazione quiz..." : "Rigenera quiz RAG"}</span>
          </button>

          {(course.lifecycle_status === "GENERATED" ||
            course.lifecycle_status === "REJECTED" ||
            course.lifecycle_status === "NEEDS_UPDATE") && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={Boolean(busyAction)}
              onClick={() => void handleTransition("UNDER_REVIEW", "Invia in revisione")}
            >
              <Send size={14} aria-hidden="true" />
              <span>
                {busyAction === "UNDER_REVIEW" ? "Invio..." : "Invia in revisione"}
              </span>
            </button>
          )}

          {course.lifecycle_status === "UNDER_REVIEW" && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={Boolean(busyAction)}
              onClick={() => void handleTransition("APPROVED", "Approva corso")}
            >
              <span>{busyAction === "APPROVED" ? "Approvazione..." : "Approva corso"}</span>
            </button>
          )}

          {course.lifecycle_status === "APPROVED" && (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={Boolean(busyAction)}
              onClick={() => void handleTransition("PUBLISHED", "Pubblica corso")}
            >
              <span>{busyAction === "PUBLISHED" ? "Pubblicazione..." : "Pubblica corso"}</span>
            </button>
          )}
        </div>
      </div>

      {isEditingCourse && (
        <form className="owner-edit-form" onSubmit={(e) => void handleSaveCourse(e)}>
          <div className="owner-edit-grid">
            <div className="form-field">
              <label htmlFor="edit-course-title">Titolo corso</label>
              <input
                id="edit-course-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>

            <div className="form-field form-field-sm">
              <label htmlFor="edit-course-difficulty">Difficoltà</label>
              <select
                id="edit-course-difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
              >
                <option value="base">base</option>
                <option value="intermedio">intermedio</option>
                <option value="avanzato">avanzato</option>
              </select>
            </div>
          </div>

          <div className="form-field">
            <label htmlFor="edit-course-description">Descrizione</label>
            <textarea
              id="edit-course-description"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-course-summary">Sintesi del corso</label>
            <textarea
              id="edit-course-summary"
              rows={2}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-course-change-note">Nota revisione</label>
            <input
              id="edit-course-change-note"
              type="text"
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
            />
          </div>

          <div className="owner-edit-actions">
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setIsEditingCourse(false)}
            >
              <X size={14} aria-hidden="true" /> Annulla
            </button>
            <button
              type="submit"
              className="btn btn-sm btn-primary"
              disabled={busyAction === "save-course"}
            >
              <Save size={14} aria-hidden="true" />
              <span>{busyAction === "save-course" ? "Salvataggio..." : "Salva modifiche corso"}</span>
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

interface OwnerLessonEditorProps {
  authContext: RequestAuthContext;
  courseId: string;
  lesson: Lesson;
  onLessonUpdated: (updated: Lesson, message: string) => void;
  onError: (message: string) => void;
}

export function OwnerLessonEditor({
  authContext,
  courseId,
  lesson,
  onLessonUpdated,
  onError,
}: OwnerLessonEditorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [title, setTitle] = useState(lesson.title);
  const [objective, setObjective] = useState(lesson.objective);
  const [explanation, setExplanation] = useState(lesson.explanation);
  const [proceduresText, setProceduresText] = useState(lesson.procedures.join("\n"));
  const [summary, setSummary] = useState(lesson.summary);
  const [changeSummary, setChangeSummary] = useState("Modifica manuale lezione (Owner)");
  const [busyMode, setBusyMode] = useState<"save" | "regen" | null>(null);

  useEffect(() => {
    setIsOpen(false);
    setTitle(lesson.title);
    setObjective(lesson.objective);
    setExplanation(lesson.explanation);
    setProceduresText(lesson.procedures.join("\n"));
    setSummary(lesson.summary);
  }, [lesson]);

  const handleSaveLesson = async (e: FormEvent) => {
    e.preventDefault();
    if (busyMode) return;
    setBusyMode("save");
    try {
      const procedures = proceduresText
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      const updated = await updateLesson(authContext, courseId, lesson.id, {
        title: title.trim(),
        objective: objective.trim(),
        explanation: explanation.trim(),
        procedures,
        summary: summary.trim(),
        change_summary: changeSummary.trim() || "Modifica manuale lezione (Owner)",
      });
      setIsOpen(false);
      onLessonUpdated(updated, "Lezione aggiornata e salvata come nuova revisione.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Errore durante il salvataggio della lezione.");
    } finally {
      setBusyMode(null);
    }
  };

  const handleRegenerateLesson = async () => {
    if (busyMode) return;
    setBusyMode("regen");
    try {
      const updated = await regenerateLesson(authContext, courseId, lesson.id);
      setIsOpen(false);
      onLessonUpdated(updated, "Lezione rigenerata dalle fonti RAG originali.");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Errore durante la rigenerazione della lezione.");
    } finally {
      setBusyMode(null);
    }
  };

  return (
    <div className="owner-lesson-controls">
      <div className="owner-authoring-actions">
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          disabled={Boolean(busyMode)}
          onClick={() => setIsOpen((prev) => !prev)}
        >
          <Pencil size={14} aria-hidden="true" />
          <span>{isOpen ? "Chiudi editor lezione" : "Modifica lezione"}</span>
        </button>

        <button
          type="button"
          className="btn btn-sm btn-secondary"
          disabled={Boolean(busyMode)}
          onClick={() => void handleRegenerateLesson()}
        >
          <RefreshCw size={14} aria-hidden="true" />
          <span>{busyMode === "regen" ? "Rigenerazione..." : "Rigenera con RAG"}</span>
        </button>
      </div>

      {isOpen && (
        <form className="owner-edit-form" onSubmit={(e) => void handleSaveLesson(e)}>
          <div className="form-field">
            <label htmlFor="edit-lesson-title">Titolo lezione</label>
            <input
              id="edit-lesson-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-lesson-objective">Obiettivo</label>
            <input
              id="edit-lesson-objective"
              type="text"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-lesson-explanation">Spiegazione (Markdown supportato)</label>
            <textarea
              id="edit-lesson-explanation"
              rows={5}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-lesson-procedures">Procedure operative (una per riga)</label>
            <textarea
              id="edit-lesson-procedures"
              rows={4}
              value={proceduresText}
              onChange={(e) => setProceduresText(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-lesson-summary">Sintesi lezione</label>
            <textarea
              id="edit-lesson-summary"
              rows={2}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="edit-lesson-note">Nota revisione</label>
            <input
              id="edit-lesson-note"
              type="text"
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
            />
          </div>

          <div className="owner-edit-actions">
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setIsOpen(false)}
            >
              <X size={14} aria-hidden="true" /> Annulla
            </button>
            <button
              type="submit"
              className="btn btn-sm btn-primary"
              disabled={busyMode === "save"}
            >
              <Save size={14} aria-hidden="true" />
              <span>{busyMode === "save" ? "Salvataggio..." : "Salva lezione"}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
