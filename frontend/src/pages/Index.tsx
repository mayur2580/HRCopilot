import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { DraftCard } from "@/components/DraftCard";
import { ChatComposer } from "@/components/ChatComposer";
import { EmptyState } from "@/components/EmptyState";
import { TypingIndicator } from "@/components/TypingIndicator";
import { Badge } from "@/components/ui/badge";

// const API_BASE = "http://127.0.0.1:8000/api";
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";
const SESSION_STORAGE_KEY = "hr-multiagent-session-id";
const RECENT_CHATS_KEY = "hr-multiagent-recent-chats";

interface RecentChat {
  id: string;
  label: string;
  timestamp: number;
}

function createSessionId() {
  return `session-${crypto.randomUUID()}`;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface EvalData {
  routing?: { confidence?: number };
  hr_response?: { overall?: number };
  email_draft?: { overall?: number };
}

interface DraftRecipient {
  full_name: string;
  email: string;
}

interface Draft {
  sender_name: string;
  sender_id: string;
  to_name: string;
  to_email: string;
  cc?: DraftRecipient[];
  subject: string;
  body: string;
}

export default function Index() {
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem(SESSION_STORAGE_KEY) || createSessionId()
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<Draft | Draft[] | null>(null);
  const [lastAgent, setLastAgent] = useState("");
  const [lastEval, setLastEval] = useState<EvalData | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);

  const [recentChats, setRecentChats] = useState<RecentChat[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENT_CHATS_KEY) || "[]");
    } catch {
      return [];
    }
  });

  const messageEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem(RECENT_CHATS_KEY, JSON.stringify(recentChats));
  }, [recentChats]);

  useEffect(() => {
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }, [sessionId]);

  useEffect(() => {
    loadSession(sessionId);
  }, [sessionId]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, draft, sessionLoading]);

  async function loadSession(id: string) {
    setSessionLoading(true);

    try {
      const response = await fetch(`${API_BASE}/chat/${id}`);
      if (!response.ok) {
        throw new Error("Failed to load session");
      }

      const data = await response.json();

      setMessages(data.messages || []);
      setDraft(data.pending_email_draft || null);
      setLastAgent(data.last_agent || "");
      setLastEval(data.last_eval || null);
    } catch {
      // Treat as a new or unavailable session
      setMessages([]);
      setDraft(null);
      setLastAgent("");
      setLastEval(null);
    } finally {
      setSessionLoading(false);
    }
  }

  // async function sendMessage(customMessage?: string) {
  //   const messageToSend = (customMessage ?? input).trim();
  //   if (!messageToSend) return;

  //   setLoading(true);

  //   try {
  //     const response = await fetch(`${API_BASE}/chat`, {
  //       method: "POST",
  //       headers: { "Content-Type": "application/json" },
  //       body: JSON.stringify({ session_id: sessionId, message: messageToSend }),
  //     });

  //     if (!response.ok) {
  //       throw new Error("Backend request failed");
  //     }

  //     const data = await response.json();

  //     setMessages(data.messages || []);
  //     setDraft(data.pending_email_draft || null);
  //     setLastAgent(data.last_agent || "");
  //     setLastEval(data.last_eval || null);
  //     setInput("");

  //     upsertRecentChat(sessionId, messageToSend);
  //   } catch {
  //     toast.error("Could not reach backend. Check that FastAPI is running on port 8000.");
  //   } finally {
  //     setLoading(false);
  //   }
  // }
  async function sendMessage(customMessage?: string) {
  const messageToSend = (customMessage ?? input).trim();
  if (!messageToSend) return;

  // ✅ 1. SHOW USER MESSAGE IMMEDIATELY
  setMessages((prev) => [
    ...prev,
    { role: "user", content: messageToSend },
  ]);

  setInput("");
  setLoading(true);

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message: messageToSend,
      }),
    });

    if (!response.ok) {
      throw new Error("Backend request failed");
    }

    const data = await response.json();

    // ✅ 2. ONLY ADD ASSISTANT MESSAGE (NOT FULL REPLACE)
    const assistantMessages = (data.messages || []).filter(
      (m: Message) => m.role === "assistant"
    );

    setMessages((prev) => [
      ...prev,
      ...assistantMessages.slice(-1), // only latest assistant reply
    ]);

    setDraft(data.pending_email_draft || null);
    setLastAgent(data.last_agent || "");
    setLastEval(data.last_eval || null);

    upsertRecentChat(sessionId, messageToSend);
  } catch {
    toast.error("Could not reach backend.");
  } finally {
    setLoading(false);
  }
}
  async function confirmDraft() {
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/chat/${sessionId}/confirm`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Could not confirm draft");
      }

      const data = await response.json();

      setMessages(data.messages || []);
      setDraft(data.pending_email_draft || null);
      setLastAgent(data.last_agent || "");
      setLastEval(data.last_eval || null);
    } catch {
      toast.error("Could not send email draft.");
    } finally {
      setLoading(false);
    }
  }

  async function cancelDraft() {
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/chat/${sessionId}/cancel`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Could not cancel draft");
      }

      const data = await response.json();

      setMessages(data.messages || []);
      setDraft(data.pending_email_draft || null);
      setLastAgent(data.last_agent || "");
      setLastEval(data.last_eval || null);
    } catch {
      toast.error("Could not cancel email draft.");
    } finally {
      setLoading(false);
    }
  }

  function upsertRecentChat(id: string, firstMessage: string) {
    setRecentChats((prev) => {
      const label =
        firstMessage.length > 40 ? `${firstMessage.slice(0, 40)}…` : firstMessage;

      const filtered = prev.filter((chat) => chat.id !== id);

      return [
        { id, label, timestamp: Date.now() },
        ...filtered,
      ].slice(0, 20);
    });
  }

  function selectChat(id: string) {
    if (id === sessionId) return;

    setSessionId(id);
    setDraft(null);
    setLastAgent("");
    setLastEval(null);
    setInput("");
  }

  function startNewSession() {
    const newId = createSessionId();

    setSessionId(newId);
    setMessages([]);
    setDraft(null);
    setLastAgent("");
    setLastEval(null);
    setInput("");
  }

  const evalSummary = useMemo(() => {
    if (!lastEval) return "No evaluation data yet.";

    const email = lastEval.email_draft;
    const hr = lastEval.hr_response;
    const routing = lastEval.routing;

    if (email?.overall) return `Email: ${email.overall}/10`;
    if (hr?.overall) return `HR: ${hr.overall}/10`;
    if (routing?.confidence) return `Routing: ${routing.confidence}/10`;

    return "Recorded";
  }, [lastEval]);

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar
          sessionId={sessionId}
          lastAgent={lastAgent}
          hasDraft={!!draft}
          evalSummary={evalSummary}
          onNewSession={startNewSession}
          recentChats={recentChats}
          onSelectChat={selectChat}
        />

        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 flex items-center gap-3 border-b border-border px-4 bg-card/50 backdrop-blur-sm">
            <SidebarTrigger />
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                Workspace
              </Badge>
              <h2 className="text-sm font-semibold text-foreground">
                HR Assistant Console
              </h2>
            </div>
          </header>

          <div className="flex-1 flex flex-col p-4 gap-4 overflow-hidden">
            <div className="flex-1 overflow-y-auto pr-2">
              {sessionLoading ? (
                <div className="h-full flex items-center justify-center">
                  <TypingIndicator />
                </div>
              ) : messages.length === 0 && !loading ? (
                <EmptyState onSuggestion={(text) => sendMessage(text)} />
              ) : (
                <>
                  {messages.map((message, index) => (
                    <ChatMessage
                      key={`${message.role}-${index}`}
                      role={message.role}
                      content={message.content}
                    />
                  ))}
                  {loading && <TypingIndicator />}
                </>
              )}

              <div ref={messageEndRef} />
            </div>

            {draft && (
              <DraftCard
                draft={draft}
                onConfirm={confirmDraft}
                onCancel={cancelDraft}
                loading={loading}
              />
            )}

            <ChatComposer
              value={input}
              onChange={setInput}
              onSend={() => sendMessage()}
              loading={loading || sessionLoading}
            />
          </div>
        </div>
      </div>
    </SidebarProvider>
  );
}