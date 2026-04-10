import { useCallback, useRef, useState } from "react";
import { Dice5 } from "lucide-react";

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

  const randomize = useCallback(() => {
    topicIndexRef.current = (topicIndexRef.current + 1) % SAMPLE_TOPICS.length;
    const next = SAMPLE_TOPICS[topicIndexRef.current];
    setTopic(next);
    inputRef.current?.focus();
  }, []);

  const onGenerate = useCallback(() => {
    start(topic, analysts);
  }, [start, topic, analysts]);

  return (
    <div className="border-t border-border bg-card/80 backdrop-blur supports-[backdrop-filter]:bg-card/60">
      <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-3 px-4 py-3 sm:gap-4 sm:px-6">
        <Input
          ref={inputRef}
          id="topic"
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Enter a research topic, e.g. Animal advocacy in Tamil Nadu"
          disabled={disabled}
          className="min-w-0 flex-1 basis-full sm:basis-auto"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !disabled) onGenerate();
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={randomize}
          disabled={disabled}
          title="Try a sample question"
          aria-label="Randomize topic"
        >
          <Dice5 className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2">
          <label
            htmlFor="max-analysts"
            className="text-xs uppercase tracking-wider text-muted-foreground"
          >
            Analysts
          </label>
          <Input
            id="max-analysts"
            type="number"
            min={1}
            max={6}
            value={analysts}
            onChange={(e) => setAnalysts(parseInt(e.target.value, 10))}
            disabled={disabled}
            className="h-10 w-16 text-center"
          />
        </div>
        <Button type="button" onClick={onGenerate} disabled={disabled}>
          Generate
        </Button>
      </div>
    </div>
  );
}
