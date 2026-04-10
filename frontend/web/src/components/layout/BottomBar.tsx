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
        <div className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-3 shadow-sm">
          <Button
            type="button"
            variant="ghost"
            onClick={randomize}
            disabled={disabled}
            title="Try a sample question"
            aria-label="Randomize topic"
            className="h-14 w-14 shrink-0 rounded-full [&_svg]:size-6"
          >
            <Dice5 />
          </Button>
          <Input
            ref={inputRef}
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Start typing..."
            disabled={disabled}
            className="h-14 min-w-0 flex-1 border-0 bg-transparent px-3 text-lg shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onGenerate();
              }
            }}
          />
          <div className="flex shrink-0 items-center gap-2 pl-1">
            <label
              htmlFor="max-analysts"
              className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
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
              className="h-11 w-16 text-center text-base"
            />
          </div>
          <Button
            type="button"
            onClick={onGenerate}
            disabled={!canSubmit}
            aria-label="Generate"
            className="h-14 w-14 shrink-0 rounded-full [&_svg]:size-6"
          >
            <ArrowRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
