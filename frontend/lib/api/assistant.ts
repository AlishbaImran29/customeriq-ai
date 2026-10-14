// AI Business Assistant service.
//
// No language model is connected. Answers are matched from a fixed set of sample
// responses so the chat UI can be exercised end to end. When the backend is
// ready, replace `getSampleAssistantReply` with a POST to /api/v1/assistant/chat
// (the backend owns the OpenAI / LangChain integration and its API keys).

import { assistantReplies } from "@/lib/mock/customer-intelligence";

export const ASSISTANT_CONNECTED = false;

export const assistantStarters = [
  "Which customers are most likely to churn?",
  "Why did revenue decrease this month?",
  "Which segment generates the highest profit?",
  "Where are our best upsell opportunities?",
];

const fallback =
  "I can only answer a fixed set of sample questions about churn, CLV, segments, retention, health scores, revenue, and recommendations. Try one of the suggested questions.";

export function getSampleAssistantReply(question: string): string {
  const q = question.toLowerCase();
  const found = assistantReplies.find((item) =>
    item.match.some((token) => q.includes(token)),
  );
  return found?.answer ?? fallback;
}