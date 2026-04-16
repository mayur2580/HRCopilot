import { Mail, Send, X } from "lucide-react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface DraftPerson {
  full_name: string;
  email: string;
}

interface Draft {
  sender_name: string;
  sender_id: string;
  to_name: string;
  to_email: string;
  cc?: DraftPerson[];
  subject: string;
  body: string;
}

interface DraftCardProps {
  draft: Draft | Draft[];
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

function DraftItem({ draft, index }: { draft: Draft; index?: number }) {
  return (
    <div className="rounded-xl bg-muted/50 border border-border p-4 space-y-2 text-sm">
      <div className="flex items-center gap-2">
        {index !== undefined && (
          <Badge variant="secondary" className="text-xs">{index}</Badge>
        )}
        <span className="font-medium text-foreground">From:</span>
        <span className="text-muted-foreground">{draft.sender_name} &lt;{draft.sender_id}&gt;</span>
      </div>
      <div>
        <span className="font-medium text-foreground">To:</span>{" "}
        <span className="text-muted-foreground">{draft.to_name} &lt;{draft.to_email}&gt;</span>
      </div>
      {draft.cc && draft.cc.length > 0 && (
        <div>
          <span className="font-medium text-foreground">CC:</span>{" "}
          <span className="text-muted-foreground">
            {draft.cc.map((p) => `${p.full_name} <${p.email}>`).join(", ")}
          </span>
        </div>
      )}
      <div>
        <span className="font-medium text-foreground">Subject:</span>{" "}
        <span className="text-foreground">{draft.subject}</span>
      </div>
      <pre className="mt-2 whitespace-pre-wrap text-sm text-foreground/80 font-sans leading-relaxed">
        {draft.body}
      </pre>
    </div>
  );
}

export function DraftCard({ draft, onConfirm, onCancel, loading }: DraftCardProps) {
  const drafts = Array.isArray(draft) ? draft : [draft];

  return (
    <Card className="border-primary/20 shadow-lg">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full gradient-brand flex items-center justify-center">
            <Mail className="h-4 w-4 text-primary-foreground" />
          </div>
          <div>
            <Badge variant="outline" className="text-xs mb-1">Pending Draft</Badge>
            <CardTitle className="text-base">Review before sending</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {drafts.map((item, i) => (
          <DraftItem
            key={`${item.to_email}-${i}`}
            draft={item}
            index={drafts.length > 1 ? i + 1 : undefined}
          />
        ))}
      </CardContent>
      <CardFooter className="gap-3 pt-0">
        <Button variant="gradient" onClick={onConfirm} disabled={loading}>
          <Send className="h-4 w-4 mr-1" /> Send email
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          <X className="h-4 w-4 mr-1" /> Cancel
        </Button>
      </CardFooter>
    </Card>
  );
}
