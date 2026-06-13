import { useState } from "react";
import { type SessionInfo } from "@/lib/api";
import { SessionCard } from "./session-card";
import { ChevronDown, ChevronRight, FolderOpen } from "lucide-react";

function shortProjectName(workDir: string): string {
  if (!workDir) return "Unknown";
  const parts = workDir.replace(/\/$/, "").split("/");
  return parts[parts.length - 1] || workDir;
}

interface ProjectGroupProps {
  workDir: string;
  sessions: SessionInfo[];
  onSelectSession: (sessionId: string) => void;
  compact?: boolean;
  searchQuery?: string;
  onSessionDeleted?: (sessionId: string) => void;
}

export function ProjectGroup({
  workDir,
  sessions,
  onSelectSession,
  compact,
  searchQuery,
  onSessionDeleted,
}: ProjectGroupProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="mb-4">
      <button
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {collapsed ? (
          <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
        )}
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <FolderOpen size={13} />
        </span>
        <span className="truncate text-sm font-medium">
          {shortProjectName(workDir)}
        </span>
        <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
          {sessions.length}
        </span>
        <span className="ml-auto hidden max-w-[300px] truncate font-mono text-[10px] text-muted-foreground md:block">
          {workDir}
        </span>
      </button>

      {!collapsed && (
        <div
          className={
            compact
              ? "mt-1 ml-6"
              : "mt-2 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 ml-6"
          }
        >
          {sessions.map((s) => (
            <SessionCard
              key={`${s.session_id}-${s.work_dir_hash}`}
              session={s}
              onSelect={() => onSelectSession(`${s.work_dir_hash}/${s.session_id}`)}
              compact={compact}
              searchQuery={searchQuery}
              onDeleted={onSessionDeleted}
            />
          ))}
        </div>
      )}
    </div>
  );
}
