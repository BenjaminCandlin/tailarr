import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CirclePause,
  Clock,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";

import { ProgressBar } from "@/components/ProgressBar";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type Job, type JobStatus } from "@/lib/api";
import { formatElapsed, timeAgo } from "@/lib/format";
import { STATUS_LABELS, isActive, stepText, useNow } from "@/lib/jobs";
import { cn } from "@/lib/utils";

const STATUS_LOOK: Record<
  JobStatus,
  { icon: LucideIcon; tone: "neutral" | "accent" | "success" | "warning" | "danger" }
> = {
  queued: { icon: Clock, tone: "neutral" },
  running: { icon: Loader2, tone: "accent" },
  done: { icon: CheckCircle2, tone: "success" },
  failed: { icon: AlertTriangle, tone: "danger" },
  cancelled: { icon: Ban, tone: "neutral" },
  interrupted: { icon: CirclePause, tone: "warning" },
};

const ICON_COLOURS: Record<string, string> = {
  neutral: "text-muted-foreground",
  accent: "text-primary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
};

function seconds(from: string, to: number): number {
  return (to - new Date(from).getTime()) / 1000;
}

function CancelButton({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.cancelJob(job.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
  if (job.cancel_requested) {
    return <p className="text-sm text-muted-foreground">Stopping…</p>;
  }
  if (!job.cancellable) {
    return (
      <p className="max-w-56 text-xs text-muted-foreground">
        This step can't be stopped safely. It only takes a moment.
      </p>
    );
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="secondary"
        size="sm"
        onClick={() => cancel.mutate()}
        disabled={cancel.isPending}
      >
        Cancel
      </Button>
      {cancel.isError && (
        <p role="alert" className="max-w-56 text-right text-xs text-destructive">
          {cancel.error.message}
        </p>
      )}
    </div>
  );
}

/** One job in the queue: what it is, how far it's got, and how it ended. */
export function JobCard({ job }: { job: Job }) {
  const active = isActive(job);
  const now = useNow(job.status === "running");
  const look = STATUS_LOOK[job.status];
  const Icon = look.icon;
  const duration =
    job.started_at && job.finished_at
      ? seconds(job.started_at, new Date(job.finished_at).getTime())
      : null;
  const took = duration === null ? null : duration < 1 ? "under a second" : formatElapsed(duration);

  return (
    <li
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
      data-testid={`job-${job.id}`}
      aria-label={`${job.title}: ${job.subject}`}
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn(
            "mt-0.5 size-5 shrink-0",
            ICON_COLOURS[look.tone],
            job.status === "running" && "motion-safe:animate-spin",
          )}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="font-medium">{job.title}</h3>
            <Badge tone={look.tone}>{STATUS_LABELS[job.status]}</Badge>
          </div>
          <p className="text-sm [overflow-wrap:anywhere]">
            {job.film_id !== null ? (
              <Link
                to={`/films/${job.film_id}`}
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                {job.subject}
              </Link>
            ) : (
              <span className="font-medium">{job.subject}</span>
            )}
          </p>
          <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{job.file_name}</p>
        </div>
        {active && (
          <div className="shrink-0">
            <CancelButton job={job} />
          </div>
        )}
      </div>

      {active && (
        <div className="flex flex-col gap-1.5 pl-8">
          <div className="flex flex-wrap justify-between gap-x-3 text-sm">
            <span>{stepText(job)}</span>
            {job.status === "running" && job.started_at && (
              <span className="text-muted-foreground tabular-nums">
                {job.progress !== null && `${Math.round(job.progress)}% · `}
                {formatElapsed(seconds(job.started_at, now))}
              </span>
            )}
          </div>
          {job.status === "running" && (
            <ProgressBar value={job.progress} label={`Progress of ${job.title}`} />
          )}
        </div>
      )}

      {!active && (
        <div className="flex flex-col gap-2 pl-8 text-sm">
          {job.error && (
            <p
              role={job.status === "failed" ? "alert" : undefined}
              className={job.status === "failed" ? "text-destructive" : "text-warning"}
            >
              {job.error}
            </p>
          )}
          {job.message && <p className="text-muted-foreground">{job.message}</p>}
          <TechnicalDetails details={job.error_details} />
          {job.finished_at && (
            <p className="text-xs text-muted-foreground">
              Finished {timeAgo(job.finished_at)}
              {took && job.status !== "cancelled" && ` · took ${took}`}
            </p>
          )}
        </div>
      )}
    </li>
  );
}
