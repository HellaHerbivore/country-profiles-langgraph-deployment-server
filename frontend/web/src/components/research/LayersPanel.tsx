import { LayerCard } from "./LayerCard";
import { LAYERS_PLACEHOLDER } from "@/lib/layers-placeholder";
import { useResearchContext } from "@/hooks/ResearchContext";

const STATIC_MACRO = `India's regulatory framework is anchored in the landmark Prevention of Cruelty to Animals Act (1960) and the constitutional duty to show compassion to living creatures. While the legislative foundation is robust, it remains hampered by archaic penalty structures that fail to provide a credible deterrent against systemic abuse. Recent judicial activism, particularly from the Supreme Court, has increasingly recognized animal sentience and personhood, though these rulings often clash with regional cultural practices. The Animal Welfare Board of India (AWBI) serves as the primary statutory advisory body, but its efficacy is frequently constrained by fluctuating political priorities and bureaucratic inertia. Consequently, the macro environment is characterized by a high degree of legal idealism versus enforcement deficit.`;

const STATIC_DATA_POINTS = ["1.4B population", "~4.5B Land Animals/Year", "62 FAOI", "32 WAPI"];

export function LayersPanel() {
  const { state } = useResearchContext();
  const { layersBriefing: briefing, layersLoading } = state;

  const meso = briefing?.meso ?? LAYERS_PLACEHOLDER.meso;
  const micro = briefing?.micro ?? LAYERS_PLACEHOLDER.micro;
  const hidden = briefing?.hidden ?? LAYERS_PLACEHOLDER.hidden;

  return (
    <section className="flex flex-col gap-6">
      {/* Static data points */}
      <div className="flex flex-wrap gap-3">
        {STATIC_DATA_POINTS.map((point) => (
          <span
            key={point}
            className="inline-flex items-center rounded-md bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground"
          >
            {point}
          </span>
        ))}
      </div>

      {/* Static macro statement */}
      <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-secondary mb-2">
          Macro Context
        </p>
        <p className="text-sm leading-relaxed text-foreground/90">
          {STATIC_MACRO}
        </p>
      </div>

      {/* Dynamic cards: Meso, Micro, Hidden */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <LayerCard tier="MESO" body={meso} isLoading={layersLoading && !briefing} />
        <LayerCard tier="MICRO" body={micro} isLoading={layersLoading && !briefing} />
        <LayerCard tier="HIDDEN" body={hidden} isLoading={layersLoading && !briefing} />
      </div>
    </section>
  );
}
