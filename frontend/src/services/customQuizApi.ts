import { buildAuthHeaders, requestJson } from "./api";
import type {
  CustomQuiz,
  CustomQuizResult,
  LearningGap,
  LearningMetrics,
  RequestAuthContext,
  UserLearningProfile,
} from "../types/platform";

export async function listUserCustomQuizzes(auth: RequestAuthContext, userId: string): Promise<CustomQuiz[]> {
  return requestJson<CustomQuiz[]>(`/api/v1/customquiz/user/${encodeURIComponent(userId)}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function generateCustomQuiz(
  auth: RequestAuthContext,
  payload: {
    user_id: string;
    num_questions?: number;
    software?: string;
    module_name?: string;
    focus_topic?: string;
    force_new?: boolean;
    run_async?: boolean;
  }
): Promise<CustomQuiz> {
  return requestJson<CustomQuiz>("/api/v1/customquiz/generate", {
    method: "POST",
    headers: buildAuthHeaders(auth),
    body: JSON.stringify(payload),
  });
}

export async function getCustomQuiz(auth: RequestAuthContext, quizId: string): Promise<CustomQuiz> {
  return requestJson<CustomQuiz>(`/api/v1/customquiz/${encodeURIComponent(quizId)}`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function submitCustomQuiz(
  auth: RequestAuthContext,
  quizId: string,
  payload: { user_id: string; answers: Record<string, string>; duration_seconds: number }
): Promise<CustomQuizResult> {
  return requestJson<CustomQuizResult>(`/api/v1/customquiz/${encodeURIComponent(quizId)}/submit`, {
    method: "POST",
    headers: buildAuthHeaders(auth),
    body: JSON.stringify(payload),
  });
}

export async function getCustomQuizResults(
  auth: RequestAuthContext,
  quizId: string,
  userId: string
): Promise<CustomQuizResult> {
  return requestJson<CustomQuizResult>(
    `/api/v1/customquiz/${encodeURIComponent(quizId)}/results?user_id=${encodeURIComponent(userId)}`,
    {
      method: "GET",
      headers: buildAuthHeaders(auth),
    }
  );
}

export async function getLearningProfile(auth: RequestAuthContext, userId: string): Promise<UserLearningProfile> {
  return requestJson<UserLearningProfile>(`/api/v1/customquiz/user/${encodeURIComponent(userId)}/learning-profile`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function getLearningMetrics(auth: RequestAuthContext, userId: string): Promise<LearningMetrics> {
  return requestJson<LearningMetrics>(`/api/v1/customquiz/user/${encodeURIComponent(userId)}/learning-metrics`, {
    method: "GET",
    headers: buildAuthHeaders(auth),
  });
}

export async function analyzeUserGaps(auth: RequestAuthContext, userId: string): Promise<LearningGap[]> {
  return requestJson<LearningGap[]>(`/api/v1/customquiz/user/${encodeURIComponent(userId)}/analyze-gaps`, {
    method: "POST",
    headers: buildAuthHeaders(auth),
    body: JSON.stringify({}),
  });
}
