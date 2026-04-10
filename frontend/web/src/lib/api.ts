// ==========================================================================
// API Layer — CONFIG, auth headers, thread & stream management.
// Ported from legacy src/api.js. Clerk token is provided via setTokenGetter()
// so this module has no React dependency.
// ==========================================================================

import { SSEParser } from "./sse-parser";

export const CONFIG = {
  SERVER_URL:
    import.meta.env.VITE_SERVER_URL ||
    "https://country-profiles-langgraph-deployment.onrender.com",
  ASSISTANT_ID: "country_profiles",
};

// ── Token injection ──
export type TokenGetterOptions = { skipCache?: boolean };
export type TokenGetter = (opts?: TokenGetterOptions) => Promise<string | null>;

let tokenGetter: TokenGetter | null = null;

export function setTokenGetter(getter: TokenGetter | null) {
  tokenGetter = getter;
}

export class SessionExpiredError extends Error {
  constructor(message = "Your session has expired. Please sign in again.") {
    super(message);
    this.name = "SessionExpiredError";
  }
}

// ── Auth Headers ──
export async function getHeaders(
  opts?: TokenGetterOptions,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (!tokenGetter) {
    throw new SessionExpiredError();
  }
  const token = await tokenGetter(opts);
  if (!token) {
    throw new SessionExpiredError();
  }
  headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function freshToken(): Promise<string | null> {
  if (!tokenGetter) return null;
  try {
    return await tokenGetter({ skipCache: true });
  } catch {
    return null;
  }
}

// ── Wake Up Server ──
export type WakeStatusCallback = (status: string) => void;
export async function wakeUpServer(
  onStatusChange?: WakeStatusCallback,
  options: { maxAttempts?: number; initialDelay?: number; maxDelay?: number } = {},
): Promise<boolean> {
  const { maxAttempts = 60, initialDelay = 2000, maxDelay = 5000 } = options;

  // Quick check — server might already be warm
  try {
    const resp = await fetch(`${CONFIG.SERVER_URL}/ok`, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    if (resp.ok) return true;
  } catch {
    // Server is cold — fall through to retry loop
  }

  onStatusChange?.("Waking up server (this may take up to 90 seconds)...");

  let delay = initialDelay;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await new Promise((r) => setTimeout(r, delay));

    try {
      const resp = await fetch(`${CONFIG.SERVER_URL}/ok`, {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      if (resp.ok) {
        onStatusChange?.("Server is ready!");
        return true;
      }
      onStatusChange?.(`Server starting up (attempt ${attempt}/${maxAttempts})...`);
    } catch {
      onStatusChange?.(`Waiting for server (attempt ${attempt}/${maxAttempts})...`);
    }

    delay = Math.min(delay * 1.2, maxDelay);
  }

  return false;
}

// ── Retry Wrapper ──
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxRetries?: number; retryDelay?: number } = {},
): Promise<T> {
  const { maxRetries = 1, retryDelay = 3000 } = options;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const isLastAttempt = attempt === maxRetries;
      const msg = (err as Error).message || "";

      if (msg.includes("401") && !isLastAttempt) {
        const token = await freshToken();
        if (!token) {
          throw new SessionExpiredError();
        }
        continue;
      }

      if (msg.includes("503") && !isLastAttempt) {
        await new Promise((r) => setTimeout(r, retryDelay));
        await freshToken();
        continue;
      }

      if (err instanceof TypeError && msg.includes("fetch") && !isLastAttempt) {
        await new Promise((r) => setTimeout(r, retryDelay));
        continue;
      }

      throw err;
    }
  }
  // Unreachable — loop either returns or throws.
  throw new Error("withRetry exhausted without result");
}

// ── Create Thread ──
export async function createThread(): Promise<string> {
  const threadId = crypto.randomUUID();
  const resp = await fetch(`${CONFIG.SERVER_URL}/threads`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      thread_id: threadId,
      metadata: { user_id: "web-user" },
      if_exists: "do_nothing",
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to create thread (${resp.status}): ${text}`);
  }
  const data = await resp.json();
  return data.thread_id;
}

// ── Stream Research ──
export type StreamCallbacks = {
  onProgress?: (percent: number, detail: string) => void;
  onAbort?: (detail: string) => void;
  onLog?: (text: string) => void;
  onStatus?: (text: string) => void;
  onLayersBriefing?: (jsonStr: string) => void;
  onContent?: (fullContent: string) => void;
};

export async function streamResearch(
  threadId: string,
  topic: string,
  maxAnalysts: number,
  callbacks: StreamCallbacks = {},
): Promise<string> {
  const resp = await fetch(`${CONFIG.SERVER_URL}/threads/${threadId}/runs/stream`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      assistant_id: CONFIG.ASSISTANT_ID,
      input: {
        topic,
        max_analysts: maxAnalysts,
      },
      config: {
        recursion_limit: 100,
      },
      stream_mode: "messages-tuple",
      stream_subgraphs: false,
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Stream request failed (${resp.status}): ${text}`);
  }
  if (!resp.body) {
    throw new Error("Stream response has no body");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();

  let fullContent = "";
  let layersBriefingSent = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    const events = parser.parseChunk(chunk);

    for (const event of events) {
      if (event.type === "error") {
        callbacks.onLog?.("Error: " + event.text);
      } else if (event.type === "tool_start") {
        callbacks.onLog?.("Using tool: " + event.name);
      } else if (event.type === "tool") {
        callbacks.onLog?.("Tool complete: " + event.name);
      } else if (event.type === "content") {
        const progressMatch = event.text.match(/\[PROGRESS:(\d+)\]\s*(.*)/);
        const abortMatch = event.text.match(/\[PROGRESS:ABORTED\]\s*(.*)/);

        if (abortMatch) {
          callbacks.onAbort?.(abortMatch[1]);
          callbacks.onLog?.(abortMatch[1] || "Research aborted");
          const afterMarker = event.text.replace(/\[PROGRESS:ABORTED\][^\n]*\n?/, "");
          if (afterMarker.trim()) fullContent += afterMarker;
        } else if (progressMatch) {
          const percent = parseInt(progressMatch[1], 10);
          const detail = progressMatch[2];
          callbacks.onProgress?.(percent, detail);
          if (detail) callbacks.onLog?.(detail);
          const afterMarker = event.text.replace(/\[PROGRESS:\d+\][^\n]*\n?/, "");
          if (afterMarker.trim()) fullContent += afterMarker;
        } else {
          fullContent += event.text;

          if (event.text.includes("Report Finalized")) {
            callbacks.onStatus?.("Report finalized, restructuring...");
            callbacks.onLog?.("Report finalized");
          } else if (event.text.includes("Structured Profile Complete")) {
            callbacks.onStatus?.("Structured profile complete!");
            callbacks.onLog?.("Structured profile generated");
          } else if (event.text.includes("ABORTED")) {
            callbacks.onStatus?.("Research aborted - not enough data");
            callbacks.onLog?.("Aborted: not enough internal knowledge");
          }
        }

        // Check accumulated content for complete layers briefing
        if (!layersBriefingSent) {
          const marker = "[LAYERS_BRIEFING]";
          const idx = fullContent.indexOf(marker);
          if (idx !== -1) {
            const jsonStr = fullContent.slice(idx + marker.length).trim();
            try {
              JSON.parse(jsonStr);
              layersBriefingSent = true;
              callbacks.onLayersBriefing?.(jsonStr);
              callbacks.onLog?.("Layers briefing received");
              fullContent = fullContent.slice(0, idx);
            } catch {
              // JSON not complete yet — keep accumulating
            }
          }
        }

        callbacks.onContent?.(fullContent);
      }
    }
  }

  return fullContent;
}

// ── Extract Report ──
export function extractReport(fullContent: string): string {
  const structuredMarker = "### 📊 Structured Profile Complete";
  const finalizedMarker = "### ✅ Report Finalized";

  let report = "";

  const structuredIdx = fullContent.lastIndexOf(structuredMarker);
  if (structuredIdx !== -1) {
    report = fullContent.slice(structuredIdx + structuredMarker.length).trim();
  } else {
    const finalizedIdx = fullContent.lastIndexOf(finalizedMarker);
    if (finalizedIdx !== -1) {
      report = fullContent.slice(finalizedIdx + finalizedMarker.length).trim();
    }
  }

  if (!report && fullContent.length > 100) {
    report = fullContent;
  }

  return report;
}

// ── Feedback ──
export type FeedbackPayload = {
  message: string;
  page_context: {
    topic: string;
    page_state: "viewing_report" | "input";
    url: string;
  };
};

export async function submitFeedback(payload: FeedbackPayload): Promise<void> {
  const resp = await fetch(`${CONFIG.SERVER_URL}/api/feedback`, {
    method: "POST",
    headers: await getHeaders(),
    body: JSON.stringify({
      message: payload.message,
      feedback_type: "general",
      page_context: payload.page_context,
    }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Feedback submission failed (${resp.status}): ${text}`);
  }
}
