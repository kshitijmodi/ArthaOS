"use client";
import { useState, useRef, useEffect } from "react";
import { Send, AlertTriangle, Sparkles, Bot } from "lucide-react";
import { sendQuery, sendFinanceCommand } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  low_confidence?: boolean;
  timestamp: Date;
  sources?: { source: string; score: number }[];
}

const MAX = 500;
const ARGS_RE = /^[a-zA-Z0-9\s.,!?'"\-_@#%&()/\\:;]+$/;

function sanitize(raw: string) {
  return raw.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "").replace(/\s+/g, " ").trim().slice(0, MAX);
}

const SUGGESTIONS = [
  "How much did I spend last month?",
  "What are my recurring charges?",
  "Show my highest expense categories",
  "Where can I reduce spending?",
  "What is my savings rate?",
];

let seq = 0;

export default function QueryInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submit = async (q: string) => {
    const s = sanitize(q);
    if (!s || loading) return;
    setMessages(prev => [...prev, { id: seq++, role: "user", content: s, timestamp: new Date() }]);
    setInput("");
    setLoading(true);
    try {
      const isFinance = s.startsWith("/finance");
      let res;
      if (isFinance) {
        const args = s.slice("/finance".length).trim();
        if (args && !ARGS_RE.test(args)) throw new Error("Query contains unsupported characters.");
        res = await sendFinanceCommand(args);
      } else {
        res = await sendQuery(s);
      }
      setMessages(prev => [...prev, {
        id: seq++, role: "assistant",
        content: res.answer,
        low_confidence: res.low_confidence,
        sources: res.sources,
        timestamp: new Date(),
      }]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        id: seq++, role: "assistant",
        content: err.message || "Sorry, couldn't process that. Check if backend is running.",
        timestamp: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input); }
  };

  return (
    <div className="flex flex-col h-full bg-bg">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-border bg-surface shrink-0">
        <div className="w-10 h-10 rounded-2xl bg-accent/10 flex items-center justify-center">
          <Bot size={18} className="text-accent" />
        </div>
        <div>
          <p className="text-sm font-bold text-tx">ArthaOS AI</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-income animate-pulse" />
            <span className="text-[11px] text-income font-medium">Online</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center py-10 animate-fade-in">
            <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mb-4 shadow-lg shadow-accent/10">
              <Sparkles size={26} className="text-accent" />
            </div>
            <h3 className="font-bold text-tx text-lg mb-1">Ask your finances anything</h3>
            <p className="text-sm text-tx-2 mb-8 text-center max-w-xs leading-relaxed">
              Use natural language or <code className="bg-elevated px-1.5 py-0.5 rounded text-accent text-xs">/finance</code> commands
            </p>
            <div className="w-full max-w-sm space-y-2">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="w-full text-left text-sm text-tx-2 hover:text-tx bg-surface hover:bg-elevated border border-border hover:border-accent/30 rounded-xl px-4 py-3 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div
            key={msg.id}
            className={cn("flex gap-3 animate-slide-up", msg.role === "user" ? "flex-row-reverse" : "flex-row")}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center shrink-0 mt-1">
                <Bot size={14} className="text-accent" />
              </div>
            )}
            <div className={cn("flex flex-col gap-1 max-w-[82%]", msg.role === "user" ? "items-end" : "items-start")}>
              <div className={cn(
                "rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
                msg.role === "user"
                  ? "bg-accent text-white rounded-tr-sm"
                  : "bg-surface border border-border text-tx rounded-tl-sm"
              )}>
                {msg.low_confidence && (
                  <div className="flex items-center gap-1.5 text-warn text-xs mb-2 pb-2 border-b border-warn/20">
                    <AlertTriangle size={11} />
                    Low confidence — verify with statements
                  </div>
                )}
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="flex flex-wrap gap-1 px-1">
                  {msg.sources.slice(0, 3).map((s, i) => (
                    <span key={i} className="text-[10px] bg-elevated text-tx-3 border border-border px-2 py-0.5 rounded-full">
                      {s.source.split("/").pop()} · {(s.score * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              )}
              <span className="text-[10px] text-tx-3 px-1">
                {msg.timestamp.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center shrink-0 mt-1">
              <Bot size={14} className="text-accent" />
            </div>
            <div className="bg-surface border border-border rounded-2xl rounded-tl-sm px-4 py-3.5">
              <div className="flex gap-1 items-center">
                {[0, 1, 2].map(i => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 bg-tx-2 rounded-full animate-bounce-dot"
                    style={{ animationDelay: `${i * 0.18}s` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-5 pt-3 border-t border-border bg-surface shrink-0">
        <div className="flex items-end gap-3 bg-bg rounded-2xl border border-border px-4 py-3 focus-within:border-accent/40 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value.slice(0, MAX))}
            onKeyDown={handleKey}
            placeholder="Ask about your finances…  (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 bg-transparent text-sm text-tx placeholder:text-tx-3 resize-none outline-none leading-relaxed max-h-32"
          />
          <button
            onClick={() => submit(input)}
            disabled={loading || !input.trim()}
            className={cn(
              "w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0",
              input.trim() && !loading
                ? "bg-accent text-white hover:bg-accent-h shadow-sm"
                : "bg-elevated text-tx-3 cursor-not-allowed"
            )}
          >
            <Send size={13} />
          </button>
        </div>
        <p className="text-[10px] text-tx-3 mt-2 text-center">
          Try <code className="bg-elevated px-1 py-0.5 rounded">/finance summary</code> for instant stats
        </p>
      </div>
    </div>
  );
}
