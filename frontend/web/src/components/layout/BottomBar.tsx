import { useCallback, useRef, useState } from "react";
import { ArrowRight, Dice5 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SAMPLE_TOPICS } from "@/lib/sample-topics";
import { useResearchContext } from "@/hooks/ResearchContext";

export function BottomBar() {
  const { state, start } = useResearchContext();
  const [topic, setTopic] = useState("");
  const [analysts, setAnalysts] = useState(3);
  const topicIndexRef = useRef(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  const disabled = state.phase === "loading" || state.phase === "streaming";
  const canSubmit = !disabled && topic.trim().length > 0;

  const randomize = useCallback(() => {
    topicIndexRef.current = (topicIndexRef.current + 1) % SAMPLE_TOPICS.length;
    const next = SAMPLE_TOPICS[topicIndexRef.current];
    setTopic(next);
    inputRef.current?.focus();
  }, []);

  const onGenerate = useCallback(() => {
    if (!canSubmit) return;
    start(topic, analysts);
  }, [canSubmit, start, topic, analysts]);

  return (
    <div className="px-4 pb-4 pt-2 sm:px-8 md:px-12 lg:px-16">
      <div className="mx-auto w-full max-w-4xl">
        <div className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-2 shadow-sm">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={randomize}
            disabled={disabled}
            title="Try a sample question"
            aria-label="Randomize topic"
            className="h-9 w-9 shrink-0 rounded-full"
          >
            <Dice5 className="h-4 w-4" />
          </Button>
          <Input
            ref={inputRef}
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Start typing..."
            disabled={disabled}
            className="h-9 min-w-0 flex-1 border-0 bg-transparent px-2 text-[0.95rem] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onGenerate();
              }
            }}
          />
          <div className="flex shrink-0 items-center gap-1.5 pl-1">
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
          <Button
            type="button"
            size="icon"
            onClick={onGenerate}
            disabled={!canSubmit}
            aria-label="Generate"
            className="h-9 w-9 shrink-0 rounded-full"
          >
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
