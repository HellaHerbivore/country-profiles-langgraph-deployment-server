import { UserButton } from "@clerk/clerk-react";
import { Menu, PanelRightOpen } from "lucide-react";

import { Button } from "@/components/ui/button";

type NavBarProps = {
  onToggleSources: () => void;
  onToggleActivity: () => void;
};

export function NavBar({ onToggleSources, onToggleActivity }: NavBarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-3 sm:px-6">
      <div className="flex items-center gap-2 sm:gap-4">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onToggleSources}
          aria-label="Open sources panel"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex items-center gap-3">
          <span className="font-serif text-lg font-medium tracking-tight text-foreground sm:text-xl">
            Country Profiles
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted-foreground">
            <img
              src="/assets/flagpedia_india.svg"
              alt="Indian flag"
              className="h-3 w-[1.1em] rounded-[1px] object-cover"
            />
            India
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onToggleActivity}
          aria-label="Open research activity panel"
        >
          <PanelRightOpen className="h-5 w-5" />
        </Button>
        <UserButton afterSignOutUrl="/" />
      </div>
    </header>
  );
}
