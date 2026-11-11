import type { Course, CourseProgressOverviewItem, UserLearningOverview } from "../types/platform";

export type ProgressStatus = "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED";

export function formatItalianDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function formatCourseTypeLabel(courseType: string): string {
  const normalized = courseType.toUpperCase();
  if (normalized === "MICRO_COURSE") return "Micro-corso";
  if (normalized === "TOPIC_PILL") return "Pillola";
  if (normalized === "FULL_COURSE") return "Corso completo";
  if (normalized === "REMEDIAL_COURSE") return "Recupero";
  return courseType;
}

export function formatLifecycleStatus(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "PUBLISHED") return "Pubblicato";
  if (normalized === "DRAFT") return "Bozza";
  if (normalized === "ARCHIVED") return "Archiviato";
  return status;
}

export function formatProgressStatus(status: ProgressStatus): string {
  if (status === "COMPLETED") return "Completato";
  if (status === "IN_PROGRESS") return "In corso";
  return "Da iniziare";
}

export function progressStatusTone(status: ProgressStatus): "success" | "info" | "neutral" {
  if (status === "COMPLETED") return "success";
  if (status === "IN_PROGRESS") return "info";
  return "neutral";
}

export function countCourseLessons(course: Course): number {
  return course.modules.reduce((acc, mod) => acc + mod.lessons.length, 0);
}

/**
 * Derive software/module tags only from real lesson sources if deterministically present.
 */
export function extractCourseSourceTags(course: Course): string[] {
  const tags = new Set<string>();
  for (const mod of course.modules) {
    for (const lesson of mod.lessons) {
      for (const src of lesson.sources ?? []) {
        const candidate = (src.document_title || "").trim();
        if (candidate) {
          const shortTag = candidate.split(/[-–:]/)[0]?.trim();
          if (shortTag && shortTag.length <= 36) {
            tags.add(shortTag);
          }
        }
      }
    }
  }
  return Array.from(tags).slice(0, 3);
}

export function getCourseProgressForId(
  course: Course,
  overview: UserLearningOverview | null
): CourseProgressOverviewItem {
  const totalLessons = countCourseLessons(course);
  const found = overview?.course_progress.find((item) => item.course_id === course.id);
  if (found) {
    return found;
  }
  return {
    course_id: course.id,
    completed_lessons: 0,
    total_lessons: totalLessons,
    completion_percentage: 0,
    status: "NOT_STARTED",
    best_quiz_percentage: null,
    last_activity_at: null,
  };
}

/**
 * Format a compact human-readable quiz source badge without folder prefixes or long paths.
 */
export function formatQuizSourceHint(docRaw?: string | null, sectionRaw?: string | null): string | null {
  const docName = (docRaw || "").split("/").pop()?.trim() || "";
  const sectionLeaf = (sectionRaw || "").split(">").pop()?.trim() || "";
  if (!docName && !sectionLeaf) return null;
  if (docName && sectionLeaf && docName.toLowerCase() !== sectionLeaf.toLowerCase()) {
    return `${docName} • ${sectionLeaf}`;
  }
  return docName || sectionLeaf;
}
