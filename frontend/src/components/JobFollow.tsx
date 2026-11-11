import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router";

import { ProgressBar } from "@/components/ProgressBar";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import type { Job } from "@/lib/api";
import { isActive, stepText, useJob } from "@/lib/jobs";

export type JobWords = {
  /** "Saving track changes" */
  running: string;
  /** "Track changes saved" */
  done: string;
  /** "Couldn't save the changes" */
  failed: string;
  /** "The changes weren't saved" */
  cancelled: string;
  /** Shown under a failure, e.g. "Your choices are still on the page." */
  afterFailure?: string;
};

/**
 * Follows one job right where the owner started it: progress while it runs, then
 * the result (with `doneExtra` for follow-up buttons) or a plain-English error.
 */
export function JobFollow({
  jobId,
  words,
  onFinished,
  doneExtra,
}: {
  jobId: number;
  words: JobWords;
  onFinished?: (job: Job) => void;
  doneExtra?: (job: Job) => ReactNode;
}) {
  const job = useJob(jobId);
  const data = job.data;
  const finished = data !== undefined && !isActive(data);
  const told = useRef(false);
  useEffect(() => {
    if (finished && data && !told.current) {
      told.current = true;
      onFinished?.(data);
    }
  }, [finished, data, onFinished]);

  if (!data) {
    return (
      <div role="status" className="rounded-lg border bg-muted/50 px-4 py-3 text-sm">
        Starting…
      </div>
    );
  }
  if (isActive(data)) {
    return (
      <div role="status" className="flex flex-col gap-2 rounded-lg border bg-muted/50 px-4 py-3">
        <p className="text-sm font-medium">{words.running}</p>
        <p className="text-sm text-muted-foreground">
          {stepText(data)}
          {data.progress !== null && data.status === "running" && ` ${Math.round(data.progress)}%`}
        </p>
        <ProgressBar value={data.progress} label={words.running} />
      </div>
    );
  }
  if (data.status === "done") {
    return (
      <div
        role="status"
        className="flex gap-3 rounded-lg border border-success/40 bg-success-soft px-4 py-3 text-sm"
      >
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
        <div className="flex min-w-0 flex-col gap-2">
          <div>
            <p className="font-medium">{words.done}</p>
            <p className="[overflow-wrap:anywhere]">{data.message}</p>
          </div>
          {doneExtra?.(data)}
        </div>
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive-soft px-4 py-3 text-sm"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
      <div className="flex min-w-0 flex-col gap-2">
        <p className="font-medium">
          {data.status === "cancelled" ? words.cancelled : words.failed}
        </p>
        <p>{data.error ?? data.message}</p>
        <TechnicalDetails details={data.error_details} />
        <p className="text-muted-foreground">
          {words.afterFailure && `${words.afterFailure} `}
          <Link to="/queue" className="text-primary underline-offset-4 hover:underline">
            See the queue
          </Link>
        </p>
      </div>
    </div>
  );
}
