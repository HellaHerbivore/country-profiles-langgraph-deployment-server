// ==========================================================================
// SSE Parser — mirrors server-side SSEParser protocol
// ==========================================================================

export class SSEParser {
    constructor() {
        this.buffer = "";
        this.seenMessageIds = new Set();
    }

    parseChunk(text) {
        this.buffer += text;
        const results = [];

        while (this.buffer.includes("\r\n\r\n")) {
            const idx = this.buffer.indexOf("\r\n\r\n");
            const eventData = this.buffer.slice(0, idx);
            this.buffer = this.buffer.slice(idx + 4);
            const result = this.parseEvent(eventData);
            if (result) results.push(result);
        }
        // Also try \n\n as delimiter (some servers use this)
        while (this.buffer.includes("\n\n")) {
            const idx = this.buffer.indexOf("\n\n");
            const eventData = this.buffer.slice(0, idx);
            this.buffer = this.buffer.slice(idx + 2);
            const result = this.parseEvent(eventData);
            if (result) results.push(result);
        }

        return results;
    }

    parseEvent(eventData) {
        const lines = eventData.trim().split("\n");
        let eventType = null;
        let data = null;

        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("event:")) eventType = trimmed.slice(6).trim();
            else if (trimmed.startsWith("data:")) data = trimmed.slice(5).trim();
        }

        if (!eventType || !data) return null;
        return this.processEvent(eventType, data);
    }

    processEvent(eventType, data) {
        if (eventType === "error") {
            return { type: "error", text: data };
        }
        if (eventType === "metadata") return null;

        if (eventType === "messages") {
            try {
                const parsed = JSON.parse(data);
                let message;
                if (Array.isArray(parsed) && parsed.length === 2) {
                    message = parsed[0];
                } else if (typeof parsed === "object" && !Array.isArray(parsed)) {
                    message = parsed;
                }
                if (message) return this.processMessage(message);
            } catch (e) {
                // skip malformed JSON
            }
        }
        return null;
    }

    processMessage(message) {
        const msgType = message.type;

        if (msgType === "tool") {
            const msgId = message.id;
            if (msgId && this.seenMessageIds.has(msgId)) return null;
            if (msgId) this.seenMessageIds.add(msgId);
            return { type: "tool", name: message.name || "Unknown" };
        }

        if (msgType === "AIMessageChunk" || msgType === "ai") {
            let content = message.content || "";
            // Gemini/Google models return content as an array of blocks
            if (Array.isArray(content)) {
                content = content.map(block =>
                    typeof block === "string" ? block : (block.text || "")
                ).join("");
            }
            if (content) return { type: "content", text: content };

            if (message.tool_calls && message.tool_calls.length > 0) {
                const tc = message.tool_calls[0];
                if (tc.name) return { type: "tool_start", name: tc.name };
            }
        }

        return null;
    }
}
