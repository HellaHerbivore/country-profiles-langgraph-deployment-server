import { useCallback, useReducer, useRef } from "react";

import {
  createThread,
  extractReport,
  freshToken,
  SessionExpiredError,
  streamResearch,
  wakeUpServer,
  withRetry,
} from "@/lib/api";
import { markdownToHtml } from "@/lib/markdown";
import {
  initialResearchState,
  type LayersBriefing,
  type ResearchState,
} from "@/types/research";

type Action =
  | { type: "START"; topic: string; analysts: number }
  | { type: "STATUS"; status: string }
  | { type: "LOG"; text: string }
  | { type: "PROGRESS"; percent: number; statusText: string }
  | { type: "ABORT"; statusText: string }
  | { type: "LAYERS_BRIEFING"; briefing: LayersBriefing }
  | { type: "REPORT_READY"; html: string }
  | { type: "NO_REPORT" }
  | { type: "ERROR"; message: string; sessionExpired?: boolean }
  | { type: "RESET" };

function reducer(state: ResearchState, action: Action): ResearchState {
  switch (action.type) {
    case "START":
      return {
        ...initialResearchState,
        phase: "loading",
        topic: action.topic,
        analysts: action.analysts,
        layersLoading: true,
        status: "Creating research thread...",
        logs: [`Topic: ${action.topic}`, `Analysts: ${action.analysts}`],
      };
    case "STATUS":
      return { ...state, status: action.status };
    case "LOG":
      return { ...state, logs: [...state.logs, action.text] };
    case "PROGRESS":
      if (action.percent <= state.progress.percent) return state;
      return {
        ...state,
        phase: "streaming",
        progress: {
          percent: action.percent,
          statusText: action.statusText || state.progress.statusText,
          aborted: false,
        },
      };
    case "ABORT":
      return {
        ...state,
        phase: "aborted",
        progress: { ...state.progress, statusText: action.statusText, aborted: true },
      };
    case "LAYERS_BRIEFING":
      return {
        ...state,
        layersLoading: false,
        layersBriefing: action.briefing,
      };
    case "REPORT_READY":
      return {
        ...state,
        phase: "done",
        reportHtml: action.html,
        status: "Research complete",
        layersLoading: false,
      };
    case "NO_REPORT":
      return {
        ...state,
        phase: "done",
        status: "Research complete (no report generated)",
        layersLoading: false,
        logs: [
          ...state.logs,
          "No report content received. The internal vaults may not have enough data on this topic.",
        ],
      };
    case "ERROR":
      return {
        ...state,
        phase: "error",
        error: action.message,
        status: "Error occurred",
        layersLoading: false,
        logs: [...state.logs, `Error: ${action.message}`],
      };
    case "RESET":
      return initialResearchState;
    default:
      return state;
  }
}

export function useResearch() {
  const [state, dispatch] = useReducer(reducer, initialResearchState);
  const runningRef = useRef(false);

  const reset = useCallback(() => {
    if (runningRef.current) return;
    dispatch({ type: "RESET" });
  }, []);

  const start = useCallback(async (topic: string, analysts: number) => {
    if (runningRef.current) return;
    const trimmed = topic.trim();
    if (!trimmed) {
      dispatch({ type: "ERROR", message: "Please enter a research topic." });
      return;
    }
    if (isNaN(analysts) || analysts < 1 || analysts > 6) {
      dispatch({ type: "ERROR", message: "Number of analysts must be between 1 and 6." });
      return;
    }

    runningRef.current = true;
    dispatch({ type: "START", topic: trimmed, analysts });

    try {
      const serverReady = await wakeUpServer((statusText) => {
        dispatch({ type: "STATUS", status: statusText });
        dispatch({ type: "LOG", text: statusText });
      });

      if (!serverReady) {
        throw new Error(
          "Server did not respond after 90 seconds. It may be experiencing issues. Please try again in a moment.",
        );
      }

      const token = await freshToken();
      if (!token) {
        throw new SessionExpiredError();
      }

      dispatch({ type: "STATUS", status: "Creating research thread..." });
      const threadId = await withRetry(() => createThread());
      dispatch({ type: "LOG", text: `Thread created: ${threadId.slice(0, 8)}...` });

      dispatch({ type: "STATUS", status: "Running research pipeline..." });
      const fullContent = await withRetry(
        () =>
          streamResearch(threadId, trimmed, analysts, {
            onProgress: (percent, detail) => {
              dispatch({ type: "PROGRESS", percent, statusText: detail });
              if (detail) dispatch({ type: "LOG", text: detail });
            },
            onAbort: (detail) => {
              dispatch({ type: "ABORT", statusText: detail });
              dispatch({ type: "LOG", text: detail || "Research aborted" });
            },
            onLog: (text) => dispatch({ type: "LOG", text }),
            onStatus: (text) => dispatch({ type: "STATUS", status: text }),
            onLayersBriefing: (jsonStr) => {
              try {
                const parsed = JSON.parse(jsonStr) as LayersBriefing;
                dispatch({ type: "LAYERS_BRIEFING", briefing: parsed });
              } catch (e) {
                console.error("Failed to parse layers briefing:", e);
              }
            },
            onContent: () => {
              /* handled via accumulated fullContent below */
            },
          }),
        { maxRetries: 1, retryDelay: 5000 },
      );

      const report = extractReport(fullContent);
      if (report) {
        dispatch({ type: "REPORT_READY", html: markdownToHtml(report) });
      } else {
        dispatch({ type: "NO_REPORT" });
      }
    } catch (err) {
      console.error(err);
      const message = (err as Error).message || "Unknown error";
      const sessionExpired =
        err instanceof SessionExpiredError ||
        message.includes("401") ||
        message.toLowerCase().includes("session has expired");
      dispatch({ type: "ERROR", message, sessionExpired });
    } finally {
      runningRef.current = false;
    }
  }, []);

  return { state, start, reset };
}
