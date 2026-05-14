import { useState, useCallback, useMemo } from "react";

import { SOURCES, selectedStoreKeys } from "@/lib/sources";

export type SourceState = Record<string, boolean>;

const COMING_SOON_IDS = new Set(SOURCES.filter((s) => s.comingSoon).map((s) => s.id));

function initialState(): SourceState {
  return Object.fromEntries(SOURCES.map((s) => [s.id, s.defaultChecked]));
}

export function useSources() {
  const [checked, setChecked] = useState<SourceState>(initialState);

  const toggle = useCallback((id: string) => {
    if (COMING_SOON_IDS.has(id)) return;
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const set = useCallback((id: string, value: boolean) => {
    if (COMING_SOON_IDS.has(id)) return;
    setChecked((prev) => ({ ...prev, [id]: value }));
  }, []);

  const storeKeys = useMemo(() => selectedStoreKeys(checked), [checked]);

  return { checked, toggle, set, storeKeys };
}
