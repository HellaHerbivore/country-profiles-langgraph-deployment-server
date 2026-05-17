import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useResearchContext } from "@/hooks/ResearchContext";
import { cn } from "@/lib/utils";

export function LoadingState() {
  const { state } = useResearchContext();
  const { progress, status, logs, topic } = state;
  const logViewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = logViewportRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  return (
    <section className="flex flex-col gap-5">
      {/* Meta card */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Research Topic
        </div>
        <div className="mt-1 break-words text-sm font-medium text-foreground">{topic}</div>
      </div>

      {/* Progress */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3 text-sm">
          <div className="flex min-w-0 items-center gap-2">
            {!progress.aborted && (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
            )}
            <span className="truncate font-medium text-foreground">{status}</span>
          </div>
          <span
            className={cn(
              "shrink-0 text-xs font-semibold",
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
      <div className="flex min-h-0 flex-col gap-2">
        <div className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground">
          Activity Log
        </div>
        <ScrollArea className="max-h-[50vh] min-h-[12rem] rounded-md border border-border bg-muted/30">
          <div ref={logViewportRef} className="flex flex-col gap-1 p-3 font-mono text-xs">
            {logs.map((entry, i) => (
              <div key={i} className="text-foreground/80">
                {entry}
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </section>
  );
}
