import { useState } from "react";
import { Info } from "lucide-react";

import { NavBar } from "./NavBar";
import { SourcesSidebar } from "./SourcesSidebar";
import { MobileSourcesSheet } from "./MobileSourcesSheet";
import { MobileActivitySheet } from "./MobileActivitySheet";
import { BottomBar } from "./BottomBar";
import { LayersPanel } from "@/components/research/LayersPanel";
import { LoadingState } from "@/components/research/LoadingState";
import { ReportSurface } from "@/components/research/ReportSurface";
import { ErrorBanner } from "@/components/research/ErrorBanner";
import { ActivitySidebar } from "@/components/research/ActivitySidebar";
import { useResearchContext } from "@/hooks/ResearchContext";
import { useSources } from "@/hooks/useSources";

export function AppShell() {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const sources = useSources();
  const { state } = useResearchContext();

  const showLoading =
    state.phase === "loading" ||
    state.phase === "streaming" ||
    state.phase === "aborted";
  const showReport = state.phase === "done" && state.reportHtml;

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_1fr] bg-background">
      <NavBar
        onToggleSources={() => setSourcesOpen(true)}
        onToggleActivity={() => setActivityOpen(true)}
      />

      <div className="grid min-h-0 grid-cols-1 md:grid-cols-[1fr_320px] lg:grid-cols-[1fr_2fr_1fr]">
        <SourcesSidebar checked={sources.checked} onToggle={sources.toggle} />

        <main className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-8 md:px-12 lg:px-16">
            <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
              <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4 text-sm text-foreground/80">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <p>
                  Tractability Assistant helps you check how well charity interventions hold up
                  against research and field data.
                </p>
              </div>
              <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4 text-sm text-foreground/80">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <p>
                  Tractability Assistant&rsquo;s speed has not yet been optimized. Keep your phone awake
                  or this page alive for about 2&ndash;3 minutes while we surface the insights.
                </p>
              </div>
              <ErrorBanner message={state.error} />
              <LayersPanel />
              {showLoading && <LoadingState />}
              {showReport && <ReportSurface />}
            </div>
          </div>
          <BottomBar selectedStores={sources.storeKeys} />
        </main>

        <ActivitySidebar />
      </div>

      <MobileSourcesSheet
        open={sourcesOpen}
        onOpenChange={setSourcesOpen}
        checked={sources.checked}
        onToggle={sources.toggle}
      />
      <MobileActivitySheet open={activityOpen} onOpenChange={setActivityOpen} />
    </div>
  );
}
