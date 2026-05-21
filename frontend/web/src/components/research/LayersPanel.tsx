const STATIC_DATA_POINTS = ["1.4B population", "~4.5B Land Animals/Year", "62 FAOI", "32 WAPI"];

// MESO / MICRO / HIDDEN dynamic layer cards are paused — the backend does not
// currently emit a [LAYERS_BRIEFING] payload. The LayerCard component, the
// LAYERS_PLACEHOLDER text, and the LayersBriefing type/state are kept in the
// codebase so the cards can be restored by re-adding the JSX block here and
// re-reading layersBriefing/layersLoading from useResearchContext().

export function LayersPanel() {
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
    </section>
  );
}
