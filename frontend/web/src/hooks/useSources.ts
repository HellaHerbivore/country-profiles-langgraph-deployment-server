import { useState, useCallback } from "react";

import { SOURCES } from "@/lib/sources";

export type SourceState = Record<string, boolean>;

function initialState(): SourceState {
  return Object.fromEntries(SOURCES.map((s) => [s.id, s.defaultChecked]));
}

export function useSources() {
  const [checked, setChecked] = useState<SourceState>(initialState);

  const toggle = useCallback((id: string) => {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const set = useCallback((id: string, value: boolean) => {
    setChecked((prev) => ({ ...prev, [id]: value }));
  }, []);

  return { checked, toggle, set };
}
