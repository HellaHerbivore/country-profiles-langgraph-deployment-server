import { useCallback, useRef, useState } from "react";
import { ArrowRight, Dice5 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SAMPLE_TOPICS } from "@/lib/sample-topics";
import { useResearchContext } from "@/hooks/ResearchContext";

export function BottomBar() {
  const { state, start } = useResearchContext();
  const [topic, setTopic] = useState("");
  const [analysts, setAnalysts] = useState(3);
  const topicIndexRef = useRef(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const disabled = state.phase === "loading" || state.phase === "streaming";
  const canSubmit = !disabled && topic.trim().length > 0;

  const randomize = useCallback(() => {
    topicIndexRef.current = (topicIndexRef.current + 1) % SAMPLE_TOPICS.length;
    const next = SAMPLE_TOPICS[topicIndexRef.current];
    setTopic(next);
    textareaRef.current?.focus();
  }, []);

  const onGenerate = useCallback(() => {
    if (!canSubmit) return;
    start(topic, analysts);
  }, [canSubmit, start, topic, analysts]);

  return (
    <div className="px-4 pb-4 pt-2 sm:px-8 md:px-12 lg:px-16">
      <div className="mx-auto w-full max-w-4xl">
        <div className="rounded-2xl border border-border bg-card shadow-sm">
          <Textarea
            ref={textareaRef}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Start typing..."
            rows={2}
            disabled={disabled}
            className="min-h-[60px] resize-none border-0 bg-transparent px-4 pt-3 pb-1 text-[0.95rem] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onGenerate();
              }
            }}
          />
          <div className="flex items-center justify-between gap-2 px-2 pb-2">
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={randomize}
                disabled={disabled}
                title="Try a sample question"
                aria-label="Randomize topic"
                className="h-9 w-9 rounded-full"
              >
                <Dice5 className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-1.5 pl-1">
                <label
                  htmlFor="max-analysts"
                  className="text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  Analysts
                </label>
                <Input
                  id="max-analysts"
                  type="number"
                  min={1}
                  max={6}
                  value={analysts}
                  onChange={(e) => setAnalysts(parseInt(e.target.value, 10) || 1)}
                  disabled={disabled}
                  className="h-8 w-14 text-center"
                />
              </div>
            </div>
            <Button
              type="button"
              size="icon"
              onClick={onGenerate}
              disabled={!canSubmit}
              aria-label="Generate"
              className="h-9 w-9 rounded-full"
            >
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
