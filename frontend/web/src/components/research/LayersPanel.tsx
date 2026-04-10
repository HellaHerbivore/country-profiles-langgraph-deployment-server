import { LayerCard } from "./LayerCard";
import { LAYERS_PLACEHOLDER } from "@/lib/layers-placeholder";
import { useResearchContext } from "@/hooks/ResearchContext";

export function LayersPanel() {
  const { state } = useResearchContext();
  const { layersBriefing: briefing, layersLoading } = state;

  const headline = briefing?.synthesis ?? LAYERS_PLACEHOLDER.headline;
  const macro = briefing?.macro ?? LAYERS_PLACEHOLDER.macro;
  const meso = briefing?.meso ?? LAYERS_PLACEHOLDER.meso;
  const micro = briefing?.micro ?? LAYERS_PLACEHOLDER.micro;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-secondary">
          How change moves through the layers
        </p>
        <h2 className="font-serif text-2xl font-medium leading-tight tracking-tight text-foreground md:text-3xl">
          {headline}
        </h2>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <LayerCard tier="MACRO" body={macro} isLoading={layersLoading && !briefing} />
        <LayerCard tier="MESO" body={meso} isLoading={layersLoading && !briefing} />
        <LayerCard tier="MICRO" body={micro} isLoading={layersLoading && !briefing} />
      </div>
    </section>
  );
}
