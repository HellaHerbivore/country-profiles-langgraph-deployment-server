import { Folder } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { SOURCES } from "@/lib/sources";
import type { SourceState } from "@/hooks/useSources";

type SourcesListProps = {
  checked: SourceState;
  onToggle: (id: string) => void;
};

export function SourcesList({ checked, onToggle }: SourcesListProps) {
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-lg font-medium text-foreground">Sources</h2>
        <Folder className="h-4 w-4 text-secondary" aria-hidden="true" />
      </div>
      <Separator />
      <ScrollArea className="-mx-2 flex-1 px-2">
        <div className="flex flex-col gap-1.5 pb-2">
          {SOURCES.map((source) => {
            const disabled = source.comingSoon;
            return (
              <label
                key={source.id}
                htmlFor={`source-${source.id}`}
                className={
                  disabled
                    ? "flex cursor-not-allowed items-center gap-3 rounded-md border border-border/60 bg-card/60 px-3 py-2.5 text-sm opacity-50"
                    : "flex cursor-pointer items-center gap-3 rounded-md border border-border/60 bg-card/60 px-3 py-2.5 text-sm transition-colors hover:bg-accent/10"
                }
              >
                <Checkbox
                  id={`source-${source.id}`}
                  checked={!disabled && !!checked[source.id]}
                  disabled={disabled}
                  onCheckedChange={() => {
                    if (!disabled) onToggle(source.id);
                  }}
                />
                <Label
                  htmlFor={`source-${source.id}`}
                  className={
                    disabled
                      ? "flex flex-1 cursor-not-allowed items-center justify-between font-normal text-foreground"
                      : "cursor-pointer font-normal text-foreground"
                  }
                >
                  <span>{source.label}</span>
                  {disabled && (
                    <span className="ml-2 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      coming soon
                    </span>
                  )}
                </Label>
              </label>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
