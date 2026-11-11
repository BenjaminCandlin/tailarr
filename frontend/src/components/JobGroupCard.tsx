import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Layers } from "lucide-react";

import { JobCard } from "@/components/JobCard";
import { ProgressBar } from "@/components/ProgressBar";
import { Button } from "@/components/ui/button";
import { api, type Job, type JobGroup } from "@/lib/api";
import { isActive } from "@/lib/jobs";

/** "3 of 10 done · 1 failed · 6 waiting". */
export function groupCounts(jobs: Job[]): string {
  const count = (status: Job["status"]) => jobs.filter((j) => j.status === status).length;
  const parts = [`${count("done")} of ${jobs.length} done`];
  const failed = count("failed") + count("interrupted");
  if (failed) parts.push(`${failed} failed`);
  if (count("running")) parts.push("1 running");
  if (count("queued")) parts.push(`${count("queued")} waiting`);
  if (count("cancelled")) parts.push(`${count("cancelled")} cancelled`);
  return parts.join(" · ");
}

/** Jobs started together (a season, a show, or a rule), shown as one card. */
export function JobGroupCard({ group, jobs }: { group: JobGroup; jobs: Job[] }) {
  const queryClient = useQueryClient();
  const active = jobs.some(isActive);
  const finished = jobs.filter((j) => !isActive(j)).length;
  const problems = jobs.some((j) => j.status === "failed" || j.status === "interrupted");
  const cancel = useMutation({
    mutationFn: () => api.cancelGroup(group.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
  return (
    <li
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
      aria-label={`Group: ${group.title}`}
      data-testid={`group-${group.id}`}
    >
      <div className="flex items-start gap-3">
        <Layers className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 className="font-medium [overflow-wrap:anywhere]">{group.title}</h3>
          <p className="text-sm text-muted-foreground" data-testid="group-counts">
            {groupCounts(jobs)}
          </p>
        </div>
        {active && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
          >
            Cancel the rest
          </Button>
        )}
      </div>
      {active && (
        <div className="pl-8">
          <ProgressBar
            value={(finished / jobs.length) * 100}
            label={`Progress of ${group.title}`}
          />
        </div>
      )}
      <details className="pl-8" open={active || problems}>
        <summary className="min-h-9 cursor-pointer py-1 text-sm text-muted-foreground">
          Show the {jobs.length} jobs
        </summary>
        <ul className="mt-2 flex flex-col gap-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </ul>
      </details>
    </li>
  );
}
