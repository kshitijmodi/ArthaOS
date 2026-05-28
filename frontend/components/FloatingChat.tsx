"use client";
import { useState } from "react";
import { MessageCircle, X, Minus } from "lucide-react";
import QueryInterface from "@/components/QueryInterface";
import { cn } from "@/lib/utils";

export default function FloatingChat() {
  const [open, setOpen] = useState(false);
  const [minimised, setMinimised] = useState(false);

  return (
    <>
      {/* Panel */}
      {open && (
        <div className={cn(
          "fixed bottom-20 right-5 z-50 flex flex-col rounded-2xl border border-border bg-surface shadow-2xl transition-all duration-200 overflow-hidden",
          minimised ? "h-12 w-72" : "w-[380px] h-[520px]"
        )}>
          {/* Title bar */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-elevated shrink-0">
            <div className="w-2 h-2 rounded-full bg-income" />
            <span className="text-sm font-semibold text-tx flex-1">Ask ArthaOS</span>
            <button
              onClick={() => setMinimised(m => !m)}
              className="p-1 text-tx-3 hover:text-tx-2 rounded-lg hover:bg-elevated transition-colors"
              title={minimised ? "Expand" : "Minimise"}
            >
              <Minus size={13} />
            </button>
            <button
              onClick={() => { setOpen(false); setMinimised(false); }}
              className="p-1 text-tx-3 hover:text-expense rounded-lg hover:bg-elevated transition-colors"
              title="Close"
            >
              <X size={13} />
            </button>
          </div>

          {/* Chat body */}
          {!minimised && (
            <div className="flex-1 min-h-0">
              <QueryInterface />
            </div>
          )}
        </div>
      )}

      {/* Floating trigger button */}
      <button
        onClick={() => { setOpen(o => !o); setMinimised(false); }}
        className={cn(
          "fixed bottom-5 right-5 z-50 flex items-center justify-center rounded-full shadow-xl transition-all duration-200",
          "w-14 h-14 bg-accent hover:bg-accent-h active:scale-95",
          open && "rotate-0"
        )}
        title="Ask ArthaOS"
        aria-label="Open AI chat"
      >
        {open
          ? <X size={22} className="text-white" />
          : <MessageCircle size={22} className="text-white" />
        }
      </button>
    </>
  );
}
