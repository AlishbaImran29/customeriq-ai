"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, RotateCcw, SendHorizontal, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/config";
import {
  ASSISTANT_MODE,
  assistantStarters,
  getAssistantStatus,
  getSampleAssistantReply,
  PROVIDER_KEY,
  sendAssistantMessage,
  type AssistantStatus,
  type ChatRole,
} from "@/lib/api/assistant";
import { cn, formatDate, formatNumber } from "@/lib/utils";

type MessageKind = "greeting" | "ai" | "system" | "sample" | "error" | "question";

type Message = {
  id: number;
  role: ChatRole;
  kind: MessageKind;
  text: string;
  note?: string;
};

type StatusState =
  | { state: "loading" }
  | { state: "ready"; status: AssistantStatus }
  | { state: "error"; message: string };

const LIVE = ASSISTANT_MODE === "live";

const greeting: Message = {
  id: 0,
  role: "assistant",
  kind: "greeting",
  text: LIVE
    ? "Hi! Ask a question about your customers. I answer from the summary figures calculated from your imported data. Customer names and emails are never shared with the AI."
    : "Hi! Ask a question about your customers. I am running in sample mode, so answers come from a fixed set of demo responses rather than a live AI model.",
};

/** Turns sent to the backend: real questions and real answers only. */
function historyFrom(messages: Message[]) {
  return messages
    .filter((m) => m.kind === "question" || m.kind === "ai" || m.kind === "system")
    .map((m) => ({ role: m.role, content: m.text }));
}

export function AssistantChat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([greeting]);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<StatusState>({ state: "loading" });
  const nextId = useRef(1);
  const logRef = useRef<HTMLDivElement>(null);

  const checkStatus = useCallback(() => {
    if (!LIVE) return;
    setStatus({ state: "loading" });
    getAssistantStatus()
      .then((s) => setStatus({ state: "ready", status: s }))
      .catch((error: unknown) =>
        setStatus({
          state: "error",
          message: error instanceof ApiError ? error.message : "Could not check the assistant status.",
        }),
      );
  }, []);

  useEffect(() => {
    if (!LIVE) return;
    let cancelled = false;
    getAssistantStatus()
      .then((s) => !cancelled && setStatus({ state: "ready", status: s }))
      .catch((error: unknown) => {
        if (cancelled) return;
        setStatus({
          state: "error",
          message: error instanceof ApiError ? error.message : "Could not check the assistant status.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages, pending]);

  const notConfigured = LIVE && status.state === "ready" && !status.status.configured;

  async function requestAnswer(conversation: Message[]) {
    setPending(true);
    try {
      const result = await sendAssistantMessage(historyFrom(conversation));
      const note =
        result.answeredBy === "ai"
          ? `AI answer from your data${result.dataAsOf ? ` as of ${formatDate(result.dataAsOf)}` : ""} · ${result.model} · can contain mistakes, so check key figures.`
          : "Automatic message · no AI was used.";
      setMessages((prev) => [
        ...prev,
        { id: nextId.current++, role: "assistant", kind: result.answeredBy, text: result.reply, note },
      ]);
    } catch (error) {
      const text =
        error instanceof ApiError
          ? error.message
          : "Something went wrong while asking the assistant.";
      setMessages((prev) => [...prev, { id: nextId.current++, role: "assistant", kind: "error", text }]);
      if (error instanceof ApiError && error.code === "assistant_not_configured") checkStatus();
    } finally {
      setPending(false);
    }
  }

  function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    const userMessage: Message = { id: nextId.current++, role: "user", kind: "question", text: question };
    setInput("");
    if (!LIVE) {
      setMessages((prev) => [
        ...prev,
        userMessage,
        {
          id: nextId.current++,
          role: "assistant",
          kind: "sample",
          text: getSampleAssistantReply(question),
          note: "Sample response · not AI-generated",
        },
      ]);
      return;
    }
    const conversation = [...messages, userMessage];
    setMessages(conversation);
    void requestAnswer(conversation);
  }

  function retry() {
    // Drop the trailing error and ask the same question again.
    const conversation = messages.filter((m, i) => !(i === messages.length - 1 && m.kind === "error"));
    setMessages(conversation);
    void requestAnswer(conversation);
  }

  const hasConversation = messages.length > 1;
  const lastIsError = messages[messages.length - 1]?.kind === "error";

  return (
    <div className="flex flex-col gap-4">
      {LIVE ? <StatusBanner status={status} onCheck={checkStatus} /> : null}

      <div
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-label="Conversation"
        aria-busy={pending}
        className="h-[420px] space-y-4 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-4"
      >
        {messages.map((message) => {
          const isUser = message.role === "user";
          const isError = message.kind === "error";
          return (
            <div key={message.id} className={cn("flex gap-3", isUser && "flex-row-reverse")}>
              <div
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  isUser ? "bg-slate-200 text-slate-700" : isError ? "bg-rose-100 text-rose-700" : "bg-teal-600 text-white",
                )}
                aria-hidden="true"
              >
                {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>
              <div className={cn("max-w-[85%]", isUser && "text-right")}>
                <p className="sr-only">{isUser ? "You said:" : isError ? "Error:" : "Assistant said:"}</p>
                <div
                  className={cn(
                    "inline-block whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-left text-sm leading-relaxed",
                    isUser
                      ? "bg-teal-600 text-white"
                      : isError
                        ? "border border-rose-200 bg-rose-50 text-rose-900"
                        : "bg-white text-slate-700 shadow-sm",
                  )}
                >
                  {message.text}
                </div>
                {message.note ? <p className="mt-1 text-[11px] text-slate-400">{message.note}</p> : null}
              </div>
            </div>
          );
        })}
        {pending ? (
          <div className="flex gap-3" role="status">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-600 text-white" aria-hidden="true">
              <Bot className="h-4 w-4" />
            </div>
            <div className="inline-flex items-center gap-2 rounded-2xl bg-white px-3.5 py-2.5 text-sm text-slate-500 shadow-sm">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Thinking…
            </div>
          </div>
        ) : null}
      </div>

      {lastIsError && !pending ? (
        <div>
          <Button variant="secondary" onClick={retry}>
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Try again
          </Button>
        </div>
      ) : null}

      {!hasConversation ? (
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">Try asking</p>
          <div className="flex flex-wrap gap-2">
            {assistantStarters.map((item) => (
              <button
                key={item}
                type="button"
                disabled={notConfigured || pending}
                onClick={() => send(item)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-600 transition hover:border-teal-300 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <label htmlFor="assistant-input" className="sr-only">
          Ask a business question
        </label>
        <Input
          id="assistant-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={notConfigured ? "AI is not configured yet" : "Ask about churn, CLV, segments, or revenue…"}
          autoComplete="off"
          maxLength={2000}
          disabled={notConfigured}
          className="h-10"
        />
        <Button type="submit" disabled={!input.trim() || pending || notConfigured} className="h-10">
          <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Ask</span>
          <span className="sr-only sm:hidden">Ask</span>
        </Button>
        {hasConversation ? (
          <Button
            type="button"
            variant="secondary"
            className="h-10"
            disabled={pending}
            onClick={() => setMessages([greeting])}
            aria-label="Clear conversation"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
          </Button>
        ) : null}
      </form>
    </div>
  );
}

function StatusBanner({ status, onCheck }: { status: StatusState; onCheck: () => void }) {
  if (status.state === "loading") {
    return (
      <p className="flex items-center gap-2 text-xs text-slate-500" role="status">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Checking the assistant…
      </p>
    );
  }
  if (status.state === "error") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900" role="alert">
        <span>{status.message}</span>
        <Button variant="secondary" onClick={onCheck}>Check again</Button>
      </div>
    );
  }
  const { provider, configured, model, dataAsOf, customerCount } = status.status;
  if (!configured) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        <span>
          <strong>AI not configured.</strong> Add <code>{PROVIDER_KEY[provider]}</code> to{" "}
          <code>backend/.env</code> and restart the backend. It needs an API account with credits
          {provider === "anthropic" ? " (separate from a Claude Pro or Max subscription)" : ""}.
        </span>
        <Button variant="secondary" onClick={onCheck}>Check again</Button>
      </div>
    );
  }
  return (
    <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
      <strong>Connected</strong> to {model}
      {dataAsOf ? ` · answering from data as of ${formatDate(dataAsOf)} (${formatNumber(customerCount)} customers)` : " · no data imported yet"}
    </p>
  );
}
