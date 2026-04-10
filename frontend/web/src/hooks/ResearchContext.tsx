import { createContext, useContext } from "react";

import type { ResearchState } from "@/types/research";

type ResearchContextValue = {
  state: ResearchState;
  start: (topic: string, analysts: number) => Promise<void>;
  reset: () => void;
};

export const ResearchContext = createContext<ResearchContextValue | null>(null);

export function useResearchContext(): ResearchContextValue {
  const ctx = useContext(ResearchContext);
  if (!ctx) {
    throw new Error("useResearchContext must be used within ResearchContext.Provider");
  }
  return ctx;
}
