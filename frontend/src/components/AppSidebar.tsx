import { Plus, Activity, Clock, FileText, Search, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
} from "@/components/ui/sidebar";
import { useState } from "react";

interface RecentChat {
  id: string;
  label: string;
  timestamp: number;
}

interface AppSidebarProps {
  sessionId: string;
  lastAgent: string;
  hasDraft: boolean;
  evalSummary: string;
  onNewSession: () => void;
  recentChats: RecentChat[];
  onSelectChat: (id: string) => void;
}

export function AppSidebar({
  sessionId,
  lastAgent,
  hasDraft,
  evalSummary,
  onNewSession,
  recentChats,
  onSelectChat,
}: AppSidebarProps) {
  const [search, setSearch] = useState("");

  const filtered = recentChats.filter((c) =>
    c.label.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Sidebar collapsible="offcanvas" className="border-r border-sidebar-border">
      <SidebarContent className="p-4 gap-5">

        {/* Brand */}
        <SidebarGroup>
          <div className="flex items-center justify-between">
            <Badge className="gradient-brand border-0 text-primary-foreground text-xs font-semibold tracking-wide uppercase">
              HR Copilot
            </Badge>
            <ThemeToggle />
          </div>
          <h1 className="text-lg font-bold text-sidebar-foreground mt-2">
            Multi-agent HR Portal
          </h1>
          <p className="text-xs text-muted-foreground leading-relaxed mt-1">
            Chat with your HR assistant, fetch employee info, and review email drafts.
          </p>
        </SidebarGroup>

        {/* New Session + Search */}
        <SidebarGroup>
          <Button
            variant="secondary"
            className="w-full"
            onClick={onNewSession}
          >
            <Plus className="h-4 w-4 mr-1" /> New chat
          </Button>

          <div className="relative mt-3">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search chats…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-xs bg-muted/50"
            />
          </div>
        </SidebarGroup>

        {/* Recent Chats */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs">Recent</SidebarGroupLabel>
          <SidebarGroupContent>
            <div className="space-y-1 mt-2 max-h-[260px] overflow-y-auto pr-1">

              {filtered.length === 0 && (
                <p className="text-xs text-muted-foreground px-2 py-3 text-center">
                  {search ? "No matching chats" : "No recent chats"}
                </p>
              )}

              {filtered.map((chat) => {
                const isActive = chat.id === sessionId;

                return (
                  <button
                    key={chat.id}
                    onClick={() => {
                      if (chat.id !== sessionId) {
                        onSelectChat(chat.id);   // 🔥 Prevent redundant reload
                      }
                    }}
                    className={`
                      w-full flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-all duration-150
                      ${
                        isActive
                          ? "bg-primary/10 text-primary border border-primary/20 font-medium"
                          : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
                      }
                    `}
                  >
                    <MessageSquare
                      className={`h-3.5 w-3.5 shrink-0 ${
                        isActive ? "text-primary" : ""
                      }`}
                    />

                    <span className="truncate flex-1">{chat.label}</span>
                  </button>
                );
              })}
            </div>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Status */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs">System Status</SidebarGroupLabel>
          <SidebarGroupContent>
            <div className="space-y-3 mt-2">

              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Activity className="h-3.5 w-3.5" /> Last agent
                </span>
                <span className="font-medium text-foreground">
                  {lastAgent || "—"}
                </span>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <FileText className="h-3.5 w-3.5" /> Draft pending
                </span>
                <Badge variant={hasDraft ? "default" : "secondary"} className="text-xs">
                  {hasDraft ? "Yes" : "No"}
                </Badge>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" /> Evaluation
                </span>
                <span className="font-medium text-foreground text-xs text-right max-w-[140px] truncate">
                  {evalSummary}
                </span>
              </div>

            </div>
          </SidebarGroupContent>
        </SidebarGroup>

      </SidebarContent>
    </Sidebar>
  );
}