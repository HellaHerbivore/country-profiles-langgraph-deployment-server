import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SourcesList } from "./SourcesList";
import type { SourceState } from "@/hooks/useSources";

type MobileSourcesSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  checked: SourceState;
  onToggle: (id: string) => void;
};

export function MobileSourcesSheet({
  open,
  onOpenChange,
  checked,
  onToggle,
}: MobileSourcesSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="panel-sources flex w-4/5 max-w-sm flex-col p-4 pt-10">
        <SheetHeader className="sr-only">
          <SheetTitle>Sources</SheetTitle>
        </SheetHeader>
        <SourcesList checked={checked} onToggle={onToggle} />
      </SheetContent>
    </Sheet>
  );
}
