import { useEffect, useRef } from "react";
import { ClipboardList } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useResearchContext } from "@/hooks/ResearchContext";
import { cn } from "@/lib/utils";

export function ActivitySidebarContent() {
  const { state } = useResearchContext();
  const { phase, progress, status, logs, topic, analysts } = state;
  const logViewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = logViewportRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  const isIdle = phase === "idle";

  if (isIdle) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-muted-foreground">
        <ClipboardList className="h-10 w-10 opacity-50" />
        <p className="text-sm">Research activity will appear here</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-5 p-4">
      {/* Meta card */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Research Topic
        </div>
        <div className="mt-1 break-words text-sm font-medium text-foreground">{topic}</div>
        <div className="mt-3 text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Analysts
        </div>
        <div className="mt-1 text-sm font-medium text-foreground">{analysts}</div>
      </div>

      {/* Progress */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-foreground">{status}</span>
          <span
            className={cn(
              "text-xs font-semibold",
              progress.aborted ? "text-destructive" : "text-primary",
            )}
          >
            {progress.aborted ? "Aborted" : `${progress.percent}%`}
          </span>
        </div>
        <Progress
          value={progress.percent}
          indicatorClassName={cn(progress.aborted && "bg-destructive")}
        />
        {progress.statusText && (
          <p className="text-xs text-muted-foreground">{progress.statusText}</p>
        )}
      </div>

      {/* Log feed */}
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Activity Log
        </div>
        <ScrollArea className="min-h-0 flex-1 rounded-md border border-border bg-muted/30">
          <div ref={logViewportRef} className="flex flex-col gap-1 p-3 font-mono text-xs">
            {logs.map((entry, i) => (
              <div key={i} className="text-foreground/80">
                {entry}
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

export function ActivitySidebar() {
  return (
    <aside className="hidden min-h-0 border-l border-border bg-card/40 lg:flex lg:flex-col">
      <ActivitySidebarContent />
    </aside>
  );
}
