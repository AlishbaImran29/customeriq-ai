"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, RotateCcw, SendHorizontal, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { assistantStarters, getSampleAssistantReply } from "@/lib/api/assistant";
import { cn } from "@/lib/utils";

type Message = { id: number; role: "user" | "assistant"; text: string };

const greeting: Message = {
  id: 0,
  role: "assistant",
  text: "Hi! Ask a question about your customers. I am running in sample mode, so answers come from a fixed set of demo responses rather than a live AI model.",
};

export function AssistantChat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([greeting]);
  const nextId = useRef(1);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages]);

  function send(text: string) {
    const question = text.trim();
    if (!question) return;
    const userId = nextId.current++;
    const replyId = nextId.current++;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text: question },
      { id: replyId, role: "assistant", text: getSampleAssistantReply(question) },
    ]);
    setInput("");
  }

  const hasConversation = messages.length > 1;

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-label="Conversation"
        className="h-[420px] space-y-4 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-4"
      >
        {messages.map((message) => {
          const isUser = message.role === "user";
          return (
            <div key={message.id} className={cn("flex gap-3", isUser && "flex-row-reverse")}>
              <div
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  isUser ? "bg-slate-200 text-slate-700" : "bg-teal-600 text-white",
                )}
                aria-hidden="true"
              >
                {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>
              <div className={cn("max-w-[85%]", isUser && "text-right")}>
                <p className="sr-only">{isUser ? "You said:" : "Assistant said:"}</p>
                <div
                  className={cn(
                    "inline-block rounded-2xl px-3.5 py-2.5 text-left text-sm leading-relaxed",
                    isUser ? "bg-teal-600 text-white" : "bg-white text-slate-700 shadow-sm",
                  )}
                >
                  {message.text}
                </div>
                {!isUser && message.id !== 0 ? (
                  <p className="mt-1 text-[11px] text-slate-400">Sample response · not AI-generated</p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {!hasConversation ? (
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">Try asking</p>
          <div className="flex flex-wrap gap-2">
            {assistantStarters.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => send(item)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-600 transition hover:border-teal-300 hover:text-teal-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
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
          placeholder="Ask about churn, CLV, segments, or revenue…"
          autoComplete="off"
          className="h-10"
        />
        <Button type="submit" disabled={!input.trim()} className="h-10">
          <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Ask</span>
          <span className="sr-only sm:hidden">Ask</span>
        </Button>
        {hasConversation ? (
          <Button
            type="button"
            variant="secondary"
            className="h-10"
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