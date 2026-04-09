// ==========================================================================
// API Layer — CONFIG, auth headers, thread & stream management
// ==========================================================================

import { SSEParser } from './sse-parser.js';

// ── Configuration ──
export const CONFIG = {
    SERVER_URL: import.meta.env.VITE_SERVER_URL || "https://country-profiles-langgraph-deployment.onrender.com",
    ASSISTANT_ID: "country_profiles",
    CLERK_TOKEN: null
};

// ── Auth Headers ──
export async function getHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (typeof clerk !== "undefined" && clerk.session) {
        const token = await clerk.session.getToken();
        CONFIG.CLERK_TOKEN = token;
    }
    if (CONFIG.CLERK_TOKEN) {
        headers["Authorization"] = "Bearer " + CONFIG.CLERK_TOKEN;
    } else if (typeof clerk === "undefined" || !clerk.session) {
        throw new Error("Your session has expired. Please sign in again.");
    }
    return headers;
}

// ── Wake Up Server ──
// Pings /ok (unauthenticated GET) to wake Render from cold start.
// Returns true if server is reachable, false if timed out.
export async function wakeUpServer(onStatusChange, options = {}) {
    const {
        maxAttempts = 30,
        initialDelay = 2000,
        maxDelay = 5000,
    } = options;

    // Quick check — server might already be warm
    try {
        const resp = await fetch(`${CONFIG.SERVER_URL}/ok`, {
            method: 'GET',
            signal: AbortSignal.timeout(3000),
        });
        if (resp.ok) return true;
    } catch {
        // Server is cold — fall through to retry loop
    }

    onStatusChange?.('Waking up server (this may take up to 90 seconds)...');

    let delay = initialDelay;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        await new Promise(r => setTimeout(r, delay));

        try {
            const resp = await fetch(`${CONFIG.SERVER_URL}/ok`, {
                method: 'GET',
                signal: AbortSignal.timeout(5000),
            });
            if (resp.ok) {
                onStatusChange?.('Server is ready!');
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

// ── Fresh Token ──
// Force-refresh the Clerk JWT so the 60-second clock starts fresh.
// Returns the token, or null if the Clerk session is gone.
export async function freshToken() {
    if (typeof clerk !== 'undefined' && clerk.session) {
        const token = await clerk.session.getToken({ skipCache: true });
        CONFIG.CLERK_TOKEN = token;
        return token;
    }
    return null;
}

// ── Retry Wrapper ──
// Handles 401 (token refresh + retry), 503 (LangGraph not ready), and network errors.
export async function withRetry(fn, options = {}) {
    const { maxRetries = 1, retryDelay = 3000 } = options;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await fn();
        } catch (err) {
            const isLastAttempt = attempt === maxRetries;
            const msg = err.message || '';

            // 401: Token expired during request — refresh and retry
            if (msg.includes('401') && !isLastAttempt) {
                const token = await freshToken();
                if (!token) {
                    throw new Error('Your session has expired. Please sign in again.');
                }
                continue;
            }

            // 503: Internal LangGraph server not ready — wait and retry
            if (msg.includes('503') && !isLastAttempt) {
                await new Promise(r => setTimeout(r, retryDelay));
                await freshToken();
                continue;
            }

            // Network error (fetch failed entirely)
            if (err instanceof TypeError && msg.includes('fetch') && !isLastAttempt) {
                await new Promise(r => setTimeout(r, retryDelay));
                continue;
            }

            // All other errors or last attempt: propagate
            throw err;
        }
    }
}




// ── Create Thread ──
export async function createThread() {
    const threadId = crypto.randomUUID();
    const resp = await fetch(`${CONFIG.SERVER_URL}/threads`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
            thread_id: threadId,
            metadata: { user_id: "web-user" },
            if_exists: "do_nothing"
        })
    });
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Failed to create thread (${resp.status}): ${text}`);
    }
    const data = await resp.json();
    return data.thread_id;
}

// ── Stream Research ──
// Accepts callback objects: { onProgress, onAbort, onLog, onStatus, onContent, onError }
export async function streamResearch(threadId, topic, maxAnalysts, callbacks = {}) {
    const resp = await fetch(`${CONFIG.SERVER_URL}/threads/${threadId}/runs/stream`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify({
            assistant_id: CONFIG.ASSISTANT_ID,
            input: {
                topic: topic,
                max_analysts: maxAnalysts
            },
            config: {
                recursion_limit: 100
            },
            stream_mode: "messages-tuple",
            stream_subgraphs: false
        })
    });

    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Stream request failed (${resp.status}): ${text}`);
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
                            // JSON is complete — fire callback and strip from fullContent
                            layersBriefingSent = true;
                            callbacks.onLayersBriefing?.(jsonStr);
                            callbacks.onLog?.("Layers briefing received");
                            fullContent = fullContent.slice(0, idx);
                        } catch (e) {
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
export function extractReport(fullContent) {
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
