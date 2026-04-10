// ==========================================================================
// SSE Parser — mirrors server-side SSEParser protocol.
// Ported from legacy src/sse-parser.js.
// ==========================================================================

export type ParsedEvent =
  | { type: "error"; text: string }
  | { type: "content"; text: string }
  | { type: "tool"; name: string }
  | { type: "tool_start"; name: string };

type RawMessage = {
  id?: string;
  type?: string;
  name?: string;
  content?: string | Array<string | { text?: string }>;
  tool_calls?: Array<{ name?: string }>;
};

export class SSEParser {
  private buffer = "";
  private seenMessageIds = new Set<string>();

  parseChunk(text: string): ParsedEvent[] {
    this.buffer += text;
    const results: ParsedEvent[] = [];

    while (this.buffer.includes("\r\n\r\n")) {
      const idx = this.buffer.indexOf("\r\n\r\n");
      const eventData = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 4);
      const result = this.parseEvent(eventData);
      if (result) results.push(result);
    }
    while (this.buffer.includes("\n\n")) {
      const idx = this.buffer.indexOf("\n\n");
      const eventData = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const result = this.parseEvent(eventData);
      if (result) results.push(result);
    }

    return results;
  }

  private parseEvent(eventData: string): ParsedEvent | null {
    const lines = eventData.trim().split("\n");
    let eventType: string | null = null;
    let data: string | null = null;

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("event:")) eventType = trimmed.slice(6).trim();
      else if (trimmed.startsWith("data:")) data = trimmed.slice(5).trim();
    }

    if (!eventType || !data) return null;
    return this.processEvent(eventType, data);
  }

  private processEvent(eventType: string, data: string): ParsedEvent | null {
    if (eventType === "error") {
      return { type: "error", text: data };
    }
    if (eventType === "metadata") return null;

    if (eventType === "messages") {
      try {
        const parsed = JSON.parse(data);
        let message: RawMessage | undefined;
        if (Array.isArray(parsed) && parsed.length === 2) {
          message = parsed[0] as RawMessage;
        } else if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
          message = parsed as RawMessage;
        }
        if (message) return this.processMessage(message);
      } catch {
        // skip malformed JSON
      }
    }
    return null;
  }

  private processMessage(message: RawMessage): ParsedEvent | null {
    const msgType = message.type;

    if (msgType === "tool") {
      const msgId = message.id;
      if (msgId && this.seenMessageIds.has(msgId)) return null;
      if (msgId) this.seenMessageIds.add(msgId);
      return { type: "tool", name: message.name || "Unknown" };
    }

    if (msgType === "AIMessageChunk" || msgType === "ai") {
      let content: string | Array<string | { text?: string }> = message.content || "";
      // Gemini/Google models return content as an array of blocks
      if (Array.isArray(content)) {
        content = content
          .map((block) => (typeof block === "string" ? block : block.text || ""))
          .join("");
      }
      if (content) return { type: "content", text: content as string };

      if (message.tool_calls && message.tool_calls.length > 0) {
        const tc = message.tool_calls[0];
        if (tc.name) return { type: "tool_start", name: tc.name };
      }
    }

    return null;
  }
}
