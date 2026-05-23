"use client";
import { useState, useRef, useEffect } from "react";
import { Send, AlertTriangle } from "lucide-react";
import { sendQuery, QueryResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  low_confidence?: boolean;
}

const SUGGESTIONS = [
  "How much did I spend last month?",
  "What are my recurring EMIs?",
  "Show my highest expenses this quarter",
  "Where can I cut spending?",
];

export default function QueryInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = async (q: string) => {
    if (!q.trim() || loading) return;
    const userMsg: Message = { role: "user", content: q };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const res = await sendQuery(q);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res.answer,
        low_confidence: res.low_confidence,
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Sorry, I couldn't process that. Please check if the backend is running.",
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5 flex flex-col h-[480px]">
      <h2 className="font-semibold text-white mb-4">Ask Anything</h2>

      <div className="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
        {messages.length === 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-xs text-white/30 mb-3">Try asking:</p>
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => submit(s)}
                className="block w-full text-left text-sm text-white/50 hover:text-white/80 hover:bg-white/5 rounded-lg px-3 py-2 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn(
              "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed",
              msg.role === "user"
                ? "bg-blue-600/80 text-white"
                : "bg-white/10 text-white/90"
            )}>
              {msg.low_confidence && (
                <div className="flex items-center gap-1 text-amber-400 text-xs mb-2">
                  <AlertTriangle size={12} />
                  <span>Low confidence — verify with your statements</span>
                </div>
              )}
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/10 rounded-xl px-4 py-3">
              <div className="flex gap-1">
                {[0,1,2].map(i => (
                  <span key={i} className="w-1.5 h-1.5 bg-white/40 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={e => { e.preventDefault(); submit(input); }}
        className="flex gap-2"
      >
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask about your finances…"
          className="flex-1 bg-white/10 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          <Send size={16} className="text-white" />
        </button>
      </form>
    </section>
  );
}
