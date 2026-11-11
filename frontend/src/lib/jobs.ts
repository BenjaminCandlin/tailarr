/** Following jobs in the queue. */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, type Job, type JobStatus } from "@/lib/api";

export const ACTIVE: JobStatus[] = ["queued", "running"];

export function isActive(job: Pick<Job, "status">): boolean {
  return ACTIVE.includes(job.status);
}

export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Waiting",
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

/** How often to ask for news: often while something runs, rarely otherwise. */
export const FAST_POLL = 1500;
export const SLOW_POLL = 10_000;

/** Number of running and waiting jobs, for the badge on Queue. */
export function useJobCounts() {
  return useQuery({
    queryKey: ["jobs", "counts"],
    queryFn: api.jobCounts,
    refetchInterval: (query) => {
      const counts = query.state.data;
      return counts && counts.running + counts.queued > 0 ? FAST_POLL : SLOW_POLL;
    },
  });
}

/** Follow one job until it finishes. */
export function useJob(id: number | null) {
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api.job(id!),
    enabled: id !== null,
    refetchInterval: (query) => {
      const job = query.state.data;
      return job && !isActive(job) ? false : 1000;
    },
  });
}

/** The current time, updated every second while `running` (for elapsed times). */
export function useNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return now;
}

/** "Saving the changes (step 2 of 3)". */
export function stepText(job: Job): string {
  if (job.status === "queued") return "Waiting for the jobs before it to finish";
  if (!job.step) return "Starting…";
  const of = job.step_count > 1 ? ` (step ${job.step_number} of ${job.step_count})` : "";
  return `${job.step}…${of}`;
}
