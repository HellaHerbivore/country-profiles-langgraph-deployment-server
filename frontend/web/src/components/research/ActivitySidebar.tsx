import { FileText } from "lucide-react";

export function ActivitySidebarContent() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-muted-foreground">
      <FileText className="h-10 w-10 opacity-50" />
      <p className="text-sm">Sources used will appear here once research begins</p>
    </div>
  );
}

export function ActivitySidebar() {
  return (
    <aside className="panel-activity hidden min-h-0 border-l border-border lg:flex lg:flex-col">
      <ActivitySidebarContent />
    </aside>
  );
}
