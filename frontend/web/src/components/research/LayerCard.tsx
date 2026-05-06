import { cn } from "@/lib/utils";

type Tier = "MESO" | "MICRO" | "HIDDEN";

type LayerCardProps = {
  tier: Tier;
  body: string;
  isLoading: boolean;
};

function boldify(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

const tierStyles: Record<Tier, string> = {
  MESO: "bg-secondary/25 text-secondary-foreground",
  MICRO: "bg-accent/15 text-accent",
  HIDDEN: "bg-primary/15 text-primary",
};

export function LayerCard({ tier, body, isLoading }: LayerCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 shadow-sm">
      <span
        className={cn(
          "inline-flex w-fit items-center rounded-md px-2 py-0.5 text-xs font-semibold uppercase tracking-wider",
          tierStyles[tier],
        )}
      >
        {tier}
      </span>
      {isLoading ? (
        <div className="flex flex-col gap-2">
          <span className="layer-shimmer h-3" />
          <span className="layer-shimmer h-3" />
          <span className="layer-shimmer h-3 w-3/4" />
        </div>
      ) : (
        <div
          className="text-sm leading-relaxed text-foreground/90"
          dangerouslySetInnerHTML={{ __html: boldify(body) }}
        />
      )}
    </div>
  );
}
