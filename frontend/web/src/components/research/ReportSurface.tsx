import { Button } from "@/components/ui/button";
import { useResearchContext } from "@/hooks/ResearchContext";

export function ReportSurface() {
  const { state, reset } = useResearchContext();

  return (
    <div className="flex flex-col gap-8">
      <div
        className="report-prose"
        dangerouslySetInnerHTML={{ __html: state.reportHtml }}
      />
      <div>
        <Button variant="outline" onClick={reset}>
          New Research
        </Button>
      </div>
    </div>
  );
}
