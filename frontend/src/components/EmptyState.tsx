import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";

const suggestions = [
  "Explain maternity leave policy",
  "Send mail to EMP0344 about pending leaves",
  "What is the onboarding process?",
  "Draft a welcome email for a new hire",
];

interface EmptyStateProps {
  onSuggestion: (text: string) => void;
}

export function EmptyState({ onSuggestion }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] text-center px-4 gap-5">
      <div className="w-14 h-14 rounded-2xl gradient-brand flex items-center justify-center shadow-lg">
        <MessageSquare className="h-7 w-7 text-primary-foreground" />
      </div>
      <div>
        <h3 className="text-lg font-semibold text-foreground mb-1">Start a conversation</h3>
        <p className="text-sm text-muted-foreground max-w-sm">
          Ask about HR policies, employee info, or instruct the assistant to draft emails.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 max-w-md">
        {suggestions.map((s) => (
          <Button
            key={s}
            variant="outline"
            size="sm"
            className="text-xs rounded-full"
            onClick={() => onSuggestion(s)}
          >
            {s}
          </Button>
        ))}
      </div>
    </div>
  );
}
