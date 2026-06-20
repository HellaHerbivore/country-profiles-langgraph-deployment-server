import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Dice5, Paperclip, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SAMPLE_TOPICS } from "@/lib/sample-topics";
import { useResearchContext } from "@/hooks/ResearchContext";

type BottomBarProps = {
  selectedStores: string[];
};

export function BottomBar({ selectedStores }: BottomBarProps) {
  const { state, start } = useResearchContext();
  const [topic, setTopic] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const topicIndexRef = useRef(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const disabled = state.phase === "loading" || state.phase === "streaming";
  const hasSources = selectedStores.length > 0;
  const canSubmit = !disabled && (topic.trim().length > 0 || file !== null) && hasSources;

  // Auto-resize the textarea to fit its content, capped at 40vh.
  // Past that cap the textarea's native scrollbar kicks in and the
  // query bar stops growing vertically.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = window.innerHeight * 0.4;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [topic]);

  const randomize = useCallback(() => {
    topicIndexRef.current = (topicIndexRef.current + 1) % SAMPLE_TOPICS.length;
    const next = SAMPLE_TOPICS[topicIndexRef.current];
    setTopic(next);
    textareaRef.current?.focus();
  }, []);

  const onGenerate = useCallback(() => {
    if (!canSubmit) return;
    start(topic, selectedStores, file);
  }, [canSubmit, start, topic, selectedStores, file]);

  const onFilePick = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    // Reset so picking the same file again still fires onChange.
    e.target.value = "";
  }, []);

  const clearFile = useCallback(() => setFile(null), []);

  return (
    <div className="px-4 pb-4 pt-2 sm:px-8 md:px-12 lg:px-16">
      <div className="mx-auto w-full max-w-4xl">
        {file && (
          <div className="mx-auto mb-2 flex w-fit items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm shadow-sm">
            <Paperclip className="size-4 shrink-0 text-muted-foreground" />
            <span className="max-w-[16rem] truncate" title={file.name}>
              {file.name}
            </span>
            <button
              type="button"
              onClick={clearFile}
              disabled={disabled}
              aria-label="Remove attached file"
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-3xl border border-border bg-card px-3 py-3 shadow-sm">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.md,.markdown,.txt"
            onChange={onFilePick}
            className="hidden"
          />
          <Button
            type="button"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            title="Attach a PDF or Markdown document"
            aria-label="Attach document"
            className="h-14 w-14 shrink-0 rounded-full [&_svg]:size-6"
          >
            <Paperclip />
          </Button>
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
          <Textarea
            ref={textareaRef}
            rows={1}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Start typing, or attach a document..."
            disabled={disabled}
            className="min-h-[3.5rem] min-w-0 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-3 py-4 text-sm leading-6 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onGenerate();
              }
            }}
          />
          <Button
            type="button"
            onClick={onGenerate}
            disabled={!canSubmit}
            aria-label="Generate"
            title={!hasSources ? "Select at least one source to begin" : undefined}
            className="h-14 w-14 shrink-0 rounded-full [&_svg]:size-6"
          >
            <ArrowRight />
          </Button>
        </div>
      </div>
    </div>
  );
}
