import { useCallback, useReducer, useRef } from "react";

import {
  createThread,
  type DocumentInput,
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
  | { type: "START"; topic: string }
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
        layersLoading: true,
        status: "Creating research thread...",
        logs: [`Topic: ${action.topic}`],
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

// Largest file we'll accept before base64-encoding (~5 MB). base64 inflates the
// payload by ~33%, and the document rides inside the JSON run request.
const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024;
const ALLOWED_DOCUMENT_EXTENSIONS = [".pdf", ".md", ".markdown", ".txt"];

function mimeForFile(file: File): string {
  if (file.type) return file.type;
  const name = file.name.toLowerCase();
  if (name.endsWith(".md") || name.endsWith(".markdown")) return "text/markdown";
  if (name.endsWith(".txt")) return "text/plain";
  if (name.endsWith(".pdf")) return "application/pdf";
  return "application/octet-stream";
}

async function fileToDocumentInput(file: File): Promise<DocumentInput> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return {
    b64: btoa(binary),
    mime: mimeForFile(file),
    filename: file.name,
  };
}

export function useResearch() {
  const [state, dispatch] = useReducer(reducer, initialResearchState);
  const runningRef = useRef(false);

  const reset = useCallback(() => {
    if (runningRef.current) return;
    dispatch({ type: "RESET" });
  }, []);

  const start = useCallback(async (topic: string, selectedStores: string[], file?: File | null) => {
    if (runningRef.current) return;
    const trimmed = topic.trim();
    if (!trimmed && !file) {
      dispatch({ type: "ERROR", message: "Please enter a research topic or attach a document." });
      return;
    }
    if (!selectedStores || selectedStores.length === 0) {
      dispatch({ type: "ERROR", message: "Please select at least one source." });
      return;
    }

    let document: DocumentInput | null = null;
    if (file) {
      const name = file.name.toLowerCase();
      if (!ALLOWED_DOCUMENT_EXTENSIONS.some((ext) => name.endsWith(ext))) {
        dispatch({ type: "ERROR", message: "Unsupported file type. Attach a PDF, Markdown, or text file." });
        return;
      }
      if (file.size > MAX_DOCUMENT_BYTES) {
        dispatch({ type: "ERROR", message: "File is too large (max 5 MB)." });
        return;
      }
      try {
        document = await fileToDocumentInput(file);
      } catch {
        dispatch({ type: "ERROR", message: "Could not read the attached file." });
        return;
      }
    }

    runningRef.current = true;
    dispatch({ type: "START", topic: trimmed || file?.name || "Attached document" });

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
          streamResearch(threadId, trimmed, selectedStores, document, {
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
