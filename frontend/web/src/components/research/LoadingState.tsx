import { Loader2 } from "lucide-react";

export function LoadingState() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-6 text-center">
      <Loader2 className="h-7 w-7 animate-spin text-primary" />
      <p className="font-serif text-xl text-muted-foreground">
        Compiling your briefing&hellip;
      </p>
    </div>
  );
}
