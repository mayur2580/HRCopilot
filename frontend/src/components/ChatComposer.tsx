import { Send } from "lucide-react";
import { useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";

interface ChatComposerProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  loading: boolean;
}

export function ChatComposer({ value, onChange, onSend, loading }: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="flex items-end gap-3 rounded-2xl border border-border bg-card p-3 shadow-sm">
      <textarea
        ref={textareaRef}
        className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none min-h-[40px] max-h-[160px] py-2 px-1"
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your HR question or email instruction..."
      />
      <div className="flex flex-col items-center gap-1">
        <Button
          variant="gradient"
          size="icon"
          onClick={onSend}
          disabled={loading || !value.trim()}
          className="rounded-xl"
        >
          <Send className="h-4 w-4" />
        </Button>
        <span className="text-[10px] text-muted-foreground hidden sm:block">⏎ Send</span>
      </div>
    </div>
  );
}
