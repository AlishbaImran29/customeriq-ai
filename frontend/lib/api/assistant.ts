// AI Business Assistant service.
//
// Live mode: questions go to POST /api/v1/assistant/chat. The backend owns the
// AI provider key (Anthropic Claude by default; never sent to the browser),
// answers only from computed summary figures, and never sends customer names or
// emails to the AI provider.
// Demo mode: answers are matched from a fixed set of sample responses.

import { API_MODE, apiGet, apiPostJson } from "@/lib/api/config";
import { assistantReplies } from "@/lib/mock/customer-intelligence";

export const ASSISTANT_MODE = API_MODE;

export const assistantStarters = [
  "Which customers are most likely to churn?",
  "Why did revenue decrease this month?",
  "Which segment generates the highest profit?",
  "Where are our best upsell opportunities?",
];

export type ChatRole = "user" | "assistant";

export type ChatReply = {
  reply: string;
  /** "ai" = generated from your data; "system" = fixed message, no AI used. */
  answeredBy: "ai" | "system";
  model: string | null;
  dataAsOf: string | null;
  customerCount: number;
};

export type AiProvider = "anthropic" | "openai";

export const PROVIDER_KEY: Record<AiProvider, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
};

export type AssistantStatus = {
  provider: AiProvider;
  configured: boolean;
  model: string | null;
  dataAsOf: string | null;
  customerCount: number;
};

/** GET /api/v1/assistant/status — does not call the AI provider. */
export function getAssistantStatus(): Promise<AssistantStatus> {
  return apiGet<AssistantStatus>("/api/v1/assistant/status");
}

/** POST /api/v1/assistant/chat with the conversation so far (last item = question). */
export function sendAssistantMessage(
  messages: { role: ChatRole; content: string }[],
): Promise<ChatReply> {
  return apiPostJson<ChatReply>("/api/v1/assistant/chat", { messages });
}

const fallback =
  "I can only answer a fixed set of sample questions about churn, CLV, segments, retention, health scores, revenue, and recommendations. Try one of the suggested questions.";

/** Demo mode only: keyword-matched sample answer (not AI-generated). */
export function getSampleAssistantReply(question: string): string {
  const q = question.toLowerCase();
  const found = assistantReplies.find((item) =>
    item.match.some((token) => q.includes(token)),
  );
  return found?.answer ?? fallback;
}
