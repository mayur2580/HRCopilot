import { Bot } from "lucide-react";

export function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
        <Bot className="h-4 w-4 text-secondary-foreground" />
      </div>
      <div className="rounded-2xl bg-assistant-bubble border border-border px-4 py-3 flex items-center gap-1.5">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  );
}
