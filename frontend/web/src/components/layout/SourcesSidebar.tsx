import { SourcesList } from "./SourcesList";
import type { SourceState } from "@/hooks/useSources";

type SourcesSidebarProps = {
  checked: SourceState;
  onToggle: (id: string) => void;
};

export function SourcesSidebar({ checked, onToggle }: SourcesSidebarProps) {
  return (
    <aside className="panel-sources hidden min-h-0 border-r border-border p-4 lg:flex lg:flex-col">
      <SourcesList checked={checked} onToggle={onToggle} />
    </aside>
  );
}
