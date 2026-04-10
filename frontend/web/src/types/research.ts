export type ResearchPhase =
  | "idle"
  | "loading"
  | "streaming"
  | "done"
  | "error"
  | "aborted";

export type LayersBriefing = {
  synthesis?: string;
  macro?: string;
  meso?: string;
  micro?: string;
};

export type ResearchState = {
  phase: ResearchPhase;
  topic: string;
  analysts: number;
  progress: {
    percent: number;
    statusText: string;
    aborted: boolean;
  };
  status: string;
  logs: string[];
  layersBriefing: LayersBriefing | null;
  layersLoading: boolean;
  reportHtml: string;
  error: string | null;
};

export const initialResearchState: ResearchState = {
  phase: "idle",
  topic: "",
  analysts: 3,
  progress: { percent: 0, statusText: "", aborted: false },
  status: "",
  logs: [],
  layersBriefing: null,
  layersLoading: false,
  reportHtml: "",
  error: null,
};
