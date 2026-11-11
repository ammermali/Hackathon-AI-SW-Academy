import { buildAuthHeaders, requestJson } from "./api";
import type {
  Course,
  CourseGeneratePayload,
  CourseQuiz,
  CourseQuizSubmitResponse,
  CourseUpdatePayload,
  KnowledgeDocumentInfo,
  Lesson,
  LessonCompletionResponse,
  LessonUpdatePayload,
  RequestAuthContext,
  TrainingOpportunityItem,
  UserLearningOverview,
} from "../types/platform";

export async function listCourses(auth: RequestAuthContext, lifecycleStatus?: string): Promise<Course[]> {
  const qs = lifecycleStatus ? `?lifecycle_status=${encodeURIComponent(lifecycleStatus)}` : "";
  return requestJson<Course[]>(`/api/v1/academy/courses${qs}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getCourse(auth: RequestAuthContext, courseId: string): Promise<Course> {
  return requestJson<Course>(`/api/v1/academy/courses/${encodeURIComponent(courseId)}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function completeLesson(
  auth: RequestAuthContext,
  courseId: string,
  lessonId: string
): Promise<LessonCompletionResponse> {
  return requestJson<LessonCompletionResponse>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/lessons/${encodeURIComponent(lessonId)}/complete`,
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
    }
  );
}

export async function getUserLearningOverview(
  auth: RequestAuthContext,
  userId: string
): Promise<UserLearningOverview> {
  return requestJson<UserLearningOverview>(
    `/api/v1/academy/users/${encodeURIComponent(userId)}/learning-overview`,
    {
      method: "GET",
      headers: buildAuthHeaders(auth),
    }
  );
}

export async function submitCourseQuiz(
  auth: RequestAuthContext,
  courseId: string,
  quizId: string,
  answers: Record<string, string>
): Promise<CourseQuizSubmitResponse> {
  return requestJson<CourseQuizSubmitResponse>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/quizzes/${encodeURIComponent(quizId)}/submit`,
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
      body: JSON.stringify({ user_id: auth.userId, answers }),
    }
  );
}

const COURSE_GENERATION_TIMEOUT_MS = 180_000;

export async function listRagDocuments(auth: RequestAuthContext): Promise<KnowledgeDocumentInfo[]> {
  return requestJson<KnowledgeDocumentInfo[]>("/api/v1/rag/documents?status=indexed&limit=200", {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function listOpportunities(auth: RequestAuthContext): Promise<TrainingOpportunityItem[]> {
  return requestJson<TrainingOpportunityItem[]>("/api/v1/academy/opportunities", {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function generateCourse(
  auth: RequestAuthContext,
  payload: CourseGeneratePayload
): Promise<Course> {
  return requestJson<Course>(
    "/api/v1/academy/courses/generate",
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
      body: JSON.stringify(payload),
    },
    COURSE_GENERATION_TIMEOUT_MS
  );
}

export async function updateCourse(
  auth: RequestAuthContext,
  courseId: string,
  payload: CourseUpdatePayload
): Promise<Course> {
  return requestJson<Course>(`/api/v1/academy/courses/${encodeURIComponent(courseId)}`, {
    method: "PATCH",
    headers: buildAuthHeaders(auth),
    body: JSON.stringify(payload),
  });
}

export async function updateLesson(
  auth: RequestAuthContext,
  courseId: string,
  lessonId: string,
  payload: LessonUpdatePayload
): Promise<Lesson> {
  return requestJson<Lesson>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/lessons/${encodeURIComponent(lessonId)}`,
    {
      method: "PATCH",
      headers: buildAuthHeaders(auth),
      body: JSON.stringify(payload),
    }
  );
}

export async function regenerateLesson(
  auth: RequestAuthContext,
  courseId: string,
  lessonId: string
): Promise<Lesson> {
  return requestJson<Lesson>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/lessons/${encodeURIComponent(lessonId)}/regenerate`,
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
    },
    COURSE_GENERATION_TIMEOUT_MS
  );
}

export async function generateCourseQuiz(
  auth: RequestAuthContext,
  courseId: string,
  options: { lessonId?: string; numQuestions?: number } = {}
): Promise<CourseQuiz> {
  return requestJson<CourseQuiz>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/quizzes/generate`,
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
      body: JSON.stringify({
        lesson_id: options.lessonId ?? null,
        num_questions: options.numQuestions ?? 5,
      }),
    },
    COURSE_GENERATION_TIMEOUT_MS
  );
}

export async function transitionCourseLifecycle(
  auth: RequestAuthContext,
  courseId: string,
  targetStatus: "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "PUBLISHED",
  notes = ""
): Promise<Course> {
  return requestJson<Course>(
    `/api/v1/academy/courses/${encodeURIComponent(courseId)}/lifecycle`,
    {
      method: "POST",
      headers: buildAuthHeaders(auth),
      body: JSON.stringify({ target_status: targetStatus, notes }),
    }
  );
}
