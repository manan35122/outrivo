
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  toolCalls?: unknown[];
};

type ChatResponse = {
  reply?: string;
  tool_calls?: unknown[];
  tokens?: {
    in?: number;
    out?: number;
  };
  error?: string;
};

const API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "https://outrivo.onrender.com";

export default function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm Outrivo, your AI business assistant. I can help you discover leads, manage your sales pipeline, and prepare outreach messages. What would you like to work on?",
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState("");
  const [threadId, setThreadId] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [lastTokens, setLastTokens] = useState<{
    in?: number;
    out?: number;
  } | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Create or restore this browser's user and conversation IDs.
  useEffect(() => {
    let storedUserId = localStorage.getItem("outrivo_user_id");
    let storedThreadId = localStorage.getItem("outrivo_thread_id");

    if (!storedUserId) {
      storedUserId = `user_${crypto.randomUUID()}`;
      localStorage.setItem("outrivo_user_id", storedUserId);
    }

    if (!storedThreadId) {
      storedThreadId = `thread_${crypto.randomUUID()}`;
      localStorage.setItem("outrivo_thread_id", storedThreadId);
    }

    setUserId(storedUserId);
    setThreadId(storedThreadId);
    setReady(true);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const message = input.trim();

    if (!message || loading || !ready) return;

    setError("");
    setInput("");

    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
    ]);

    setLoading(true);

    try {
      const response = await fetch(`${API_URL.replace(/\/$/, "")}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id: userId,
          thread_id: threadId,
          message,
        }),
      });

      const data: ChatResponse = await response.json();

      if (!response.ok) {
        throw new Error(
          data.error || `The agent returned HTTP ${response.status}.`
        );
      }

      if (data.error) {
        throw new Error(data.error);
      }

      if (!data.reply) {
        throw new Error("The agent returned an empty response.");
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: data.reply!,
          toolCalls: data.tool_calls,
        },
      ]);

      setLastTokens(data.tokens || null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Something went wrong.";

      setError(
        `${message} Check that the agent API is running and accessible.`
      );
    } finally {
      setLoading(false);
    }
  }

  function startNewChat() {
    if (loading) return;

    const newThreadId = `thread_${crypto.randomUUID()}`;

    localStorage.setItem("outrivo_thread_id", newThreadId);
    setThreadId(newThreadId);

    setMessages([
      {
        role: "assistant",
        content:
          "New conversation started. What would you like me to help you with?",
      },
    ]);

    setInput("");
    setError("");
    setLastTokens(null);
  }

  return (
    <div className="flex min-h-screen bg-[#f8f8fc] text-[#17152b]">
      {/* Sidebar */}
      <aside className="hidden w-[250px] shrink-0 flex-col border-r border-[#eceaf3] bg-white px-5 py-7 md:flex">
        <Link href="/" className="mb-12 flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#7060df] text-lg font-bold text-white">
            O
          </div>
          <span className="text-xl font-bold tracking-tight">outrivo</span>
        </Link>

        <p className="mb-4 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#9995aa]">
          Workspace
        </p>

        <nav className="space-y-1">
          {[
            { label: "Dashboard", href: "/dashboard", icon: "▦" },
            { label: "AI Assistant", href: "/assistant", icon: "✦" },
            { label: "Leads", href: "/leads", icon: "◎" },
            { label: "Outreach", href: "/outreach", icon: "↗" },
            { label: "History", href: "/history", icon: "◷" },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${
                item.href === "/assistant"
                  ? "bg-[#f0edff] text-[#6957d7]"
                  : "text-[#777389] hover:bg-[#f7f6fb]"
              }`}
            >
              <span className="w-5 text-center text-lg">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="mt-auto rounded-2xl border border-[#eeeafa] bg-[#faf9ff] p-4">
          <p className="text-sm font-semibold">Outrivo AI</p>
          <p className="mt-2 text-xs leading-5 text-[#858198]">
            Your AI-powered business and sales assistant.
          </p>
        </div>
      </aside>

      {/* Chat area */}
      <main className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="flex h-[76px] shrink-0 items-center justify-between border-b border-[#eceaf3] bg-white px-5 sm:px-8">
          <div>
            <p className="text-xs text-[#9692a5]">Workspace / Assistant</p>
            <h1 className="text-lg font-bold">AI Assistant</h1>
          </div>

          <button
            onClick={startNewChat}
            disabled={loading || !ready}
            className="rounded-xl border border-[#e8e4f0] bg-white px-4 py-2.5 text-sm font-semibold text-[#6255c7] transition hover:bg-[#f7f5ff] disabled:opacity-50"
          >
            + New chat
          </button>
        </header>

        <section className="flex flex-1 flex-col">
          <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-6 sm:px-8">
            {/* Agent identity */}
            <div className="mb-6 flex items-center gap-3 rounded-2xl border border-[#eceaf3] bg-white p-4">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#7060df] text-xl text-white">
                ✦
              </div>
              <div className="flex-1">
                <p className="text-sm font-bold">Outrivo AI Agent</p>
                <p className="mt-1 text-xs text-[#9692a5]">
                  Lead discovery · Sales pipeline · Outreach
                </p>
              </div>
              <span className="flex items-center gap-2 text-xs text-[#16865c]">
                <span className="h-2 w-2 rounded-full bg-[#20b77a]" />
                {ready ? "Ready" : "Connecting"}
              </span>
            </div>

            {/* Messages */}
            <div className="flex-1 space-y-6 pb-6">
              {messages.map((message, index) => (
                <div
                  key={`${index}-${message.role}`}
                  className={`flex gap-3 ${
                    message.role === "user" ? "flex-row-reverse" : ""
                  }`}
                >
                  <div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold ${
                      message.role === "assistant"
                        ? "bg-[#7060df] text-white"
                        : "bg-[#e9e4ff] text-[#6957d7]"
                    }`}
                  >
                    {message.role === "assistant" ? "O" : "U"}
                  </div>

                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 sm:max-w-[75%] ${
                      message.role === "assistant"
                        ? "border border-[#eceaf3] bg-white"
                        : "bg-[#7060df] text-white"
                    }`}
                  >
                    <p className="whitespace-pre-wrap text-sm leading-7">
                      {message.content}
                    </p>

                    {message.toolCalls && message.toolCalls.length > 0 && (
                      <details className="mt-3 border-t border-[#eeeaf3] pt-2">
                        <summary className="cursor-pointer text-xs font-semibold text-[#7060df]">
                          Tools used ({message.toolCalls.length})
                        </summary>
                        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-[#777389]">
                          {JSON.stringify(message.toolCalls, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#7060df] text-white">
                    O
                  </div>
                  <div className="rounded-2xl border border-[#eceaf3] bg-white px-4 py-3 text-sm text-[#858198]">
                    Outrivo is thinking...
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Error */}
            {error && (
              <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            {/* Message input */}
            <form
              onSubmit={sendMessage}
              className="rounded-2xl border border-[#e9e5f1] bg-white p-3 shadow-[0_5px_25px_rgba(30,20,70,0.04)]"
            >
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="Ask Outrivo to find leads, manage your pipeline..."
                rows={2}
                disabled={!ready || loading}
                className="w-full resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-[#aaa6b5] disabled:opacity-50"
              />

              <div className="flex items-center justify-between border-t border-[#f0eef5] pt-3">
                <p className="text-[11px] text-[#aaa6b5]">
                  Enter to send · Shift + Enter for a new line
                </p>
                <button
                  type="submit"
                  disabled={!input.trim() || loading || !ready}
                  className="rounded-xl bg-[#7060df] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#5e4dcc] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {loading ? "Sending..." : "Send ↑"}
                </button>
              </div>
            </form>

            <div className="mt-3 flex justify-between text-[11px] text-[#aaa6b5]">
              <span>Powered by Outrivo AI</span>
              <span>
                {lastTokens
                  ? `Tokens: ${lastTokens.in ?? 0} in / ${lastTokens.out ?? 0} out`
                  : "AI-powered business assistant"}
              </span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
