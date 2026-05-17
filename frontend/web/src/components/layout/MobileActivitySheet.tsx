import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ActivitySidebarContent } from "@/components/research/ActivitySidebar";

type MobileActivitySheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function MobileActivitySheet({ open, onOpenChange }: MobileActivitySheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="panel-activity flex w-4/5 max-w-sm flex-col p-0 pt-10">
        <SheetHeader className="sr-only">
          <SheetTitle>Sources used</SheetTitle>
        </SheetHeader>
        <ActivitySidebarContent />
      </SheetContent>
    </Sheet>
  );
}
