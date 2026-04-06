// ==========================================================================
// API Layer — CONFIG, auth headers, thread & stream management
// ==========================================================================

import { SSEParser } from './sse-parser.js';

// ── Configuration ──
export const CONFIG = {
    SERVER_URL: "https://country-profiles-langgraph-deployment.onrender.com",
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
