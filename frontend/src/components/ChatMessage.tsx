import { Bot, User, Copy, Pencil, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useState } from "react";
import { Button } from "@/components/ui/button";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  onEdit?: (newContent: string) => void;
}

export function ChatMessage({ role, content, onEdit }: ChatMessageProps) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(content);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveEdit = () => {
    onEdit?.(editValue);
    setEditing(false);
  };

  return (
    <div className={`flex gap-3 mb-4 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "gradient-brand" : "bg-secondary"
        }`}
      >
        {isUser ? (
          <User className="h-4 w-4 text-primary-foreground" />
        ) : (
          <Bot className="h-4 w-4 text-secondary-foreground" />
        )}
      </div>

      <div
        className={`group relative max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-user-bubble text-user-bubble-foreground"
            : "bg-assistant-bubble text-assistant-bubble-foreground border border-border"
        }`}
      >
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
          {isUser ? "You" : "Assistant"}
        </div>

        {editing ? (
          <div className="space-y-2">
            <textarea
              className="w-full bg-background border border-input rounded-lg p-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              rows={3}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveEdit}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setEditValue(content); }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
            {isUser ? (
              <p className="whitespace-pre-wrap m-0">{content}</p>
            ) : (
              <ReactMarkdown>{content}</ReactMarkdown>
            )}
          </div>
        )}

        {!editing && (
          <div className="absolute -bottom-1 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCopy}>
              {copied ? <Check className="h-3 w-3 text-accent" /> : <Copy className="h-3 w-3" />}
            </Button>
            {isUser && onEdit && (
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditing(true)}>
                <Pencil className="h-3 w-3" />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
