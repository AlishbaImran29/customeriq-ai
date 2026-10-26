// AI Business Assistant service.
//
// Live mode: questions go to POST /api/v1/assistant/chat. The backend owns the
// AI provider key (Anthropic Claude by default; never sent to the browser),
// answers only from computed summary figures, and never sends customer names or
// emails to the AI provider.
// Demo mode (no backend): a fixed message, nothing is answered.

import { API_MODE, apiGet, apiPostJson } from "@/lib/api/config";

export const ASSISTANT_MODE = API_MODE;

export const assistantStarters = [
  "Which customers are most likely to churn?",
  "Why did revenue change this month?",
  "Which segment earns the most revenue?",
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

const fallback = "The assistant answers from your imported data, so it needs the backend. Connect the backend to use it.";

/** Demo mode only: there is no data to answer from. */
export function getSampleAssistantReply(): string {
  return fallback;
}
