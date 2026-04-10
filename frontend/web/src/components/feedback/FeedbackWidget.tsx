import { useCallback, useState } from "react";
import { MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { submitFeedback } from "@/lib/api";
import { useResearchContext } from "@/hooks/ResearchContext";

export function FeedbackWidget() {
  const { state } = useResearchContext();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "success" | "error">("idle");

  const onSubmit = useCallback(async () => {
    const trimmed = message.trim();
    if (!trimmed) return;
    setStatus("sending");
    try {
      await submitFeedback({
        message: trimmed,
        page_context: {
          topic: state.topic || "",
          page_state: state.phase === "done" ? "viewing_report" : "input",
          url: window.location.href,
        },
      });
      setMessage("");
      setStatus("success");
      setTimeout(() => setStatus("idle"), 2500);
    } catch (err) {
      console.error("Feedback submission error:", err);
      setStatus("error");
      setTimeout(() => setStatus("idle"), 3000);
    }
  }, [message, state.topic, state.phase]);

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-24 right-4 z-40 shadow-lg sm:bottom-28 sm:right-6"
      >
        <MessageSquare className="h-4 w-4" />
        Feedback
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-4 sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Share Feedback</SheetTitle>
          </SheetHeader>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="What's stopping you from using Country Profiles again? What would bring you back to Country Profiles?"
            rows={6}
            className="min-h-[140px]"
            disabled={status === "sending"}
          />
          <Button onClick={onSubmit} disabled={status === "sending" || !message.trim()}>
            {status === "sending" ? "Sending..." : "Send Feedback"}
          </Button>
          {status === "success" && (
            <div className="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-primary">
              Thank you for your feedback!
            </div>
          )}
          {status === "error" && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Feedback failed to send. Please try again.
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
