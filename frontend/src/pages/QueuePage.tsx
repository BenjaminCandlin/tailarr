import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ListOrdered, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { JobCard } from "@/components/JobCard";
import { JobGroupCard } from "@/components/JobGroupCard";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Job, type JobGroup } from "@/lib/api";
import { FAST_POLL, SLOW_POLL, isActive } from "@/lib/jobs";

type Entry = { job: Job } | { group: JobGroup; jobs: Job[] };

/** Jobs in order, with jobs of the same group (a season, a show, a rule) kept together. */
function entries(jobs: Job[], groups: JobGroup[]): Entry[] {
  const byId = new Map(groups.map((g) => [g.id, g]));
  const out: Entry[] = [];
  const seen = new Map<string, { group: JobGroup; jobs: Job[] }>();
  for (const job of jobs) {
    const group = job.group_id ? byId.get(job.group_id) : undefined;
    if (!group) {
      out.push({ job });
      continue;
    }
    let entry = seen.get(group.id);
    if (!entry) {
      entry = { group, jobs: [] };
      seen.set(group.id, entry);
      out.push(entry);
    }
    entry.jobs.push(job);
  }
  return out;
}

function isRunning(entry: Entry): boolean {
  return "job" in entry ? isActive(entry.job) : entry.jobs.some(isActive);
}

function EntryCard({ entry }: { entry: Entry }) {
  if ("job" in entry) return <JobCard job={entry.job} />;
  return <JobGroupCard group={entry.group} jobs={entry.jobs} />;
}

const DESCRIPTION = "Jobs that are waiting, running or finished. One job runs at a time.";

export function QueuePage() {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs", "list"],
    queryFn: api.jobs,
    refetchInterval: (query) => {
      const counts = query.state.data?.counts;
      return counts && counts.running + counts.queued > 0 ? FAST_POLL : SLOW_POLL;
    },
  });
  const clear = useMutation({
    mutationFn: api.clearFinishedJobs,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  if (jobs.isPending) {
    return (
      <>
        <PageHeader title="Queue" description={DESCRIPTION} />
        <div className="flex flex-col gap-3" aria-busy="true">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      </>
    );
  }
  if (jobs.isError) {
    return (
      <>
        <PageHeader title="Queue" description={DESCRIPTION} />
        <div
          role="alert"
          className="flex gap-3 rounded-lg border border-warning/40 bg-warning-soft p-4 text-sm"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <p>{jobs.error.message}</p>
        </div>
      </>
    );
  }

  const all = entries(jobs.data.jobs, jobs.data.groups ?? []);
  const active = all.filter(isRunning);
  const finished = all.filter((entry) => !isRunning(entry));

  return (
    <>
      <PageHeader title="Queue" description={DESCRIPTION} />
      {jobs.data.jobs.length === 0 ? (
        <EmptyState icon={ListOrdered} title="Nothing in the queue">
          <p>
            When you ask Tailarr to change a file, the job shows up here with its progress. Your
            original files are never changed without asking you first.
          </p>
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-8">
          <section aria-labelledby="queue-now">
            <h2 id="queue-now" className="mb-3 text-sm font-semibold">
              Running and waiting{" "}
              <span className="font-normal text-muted-foreground">({active.length})</span>
            </h2>
            {active.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing is running right now.</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {active.map((entry) => (
                  <EntryCard key={"job" in entry ? entry.job.id : entry.group.id} entry={entry} />
                ))}
              </ul>
            )}
          </section>
          {finished.length > 0 && (
            <section aria-labelledby="queue-finished">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 id="queue-finished" className="text-sm font-semibold">
                  Finished{" "}
                  <span className="font-normal text-muted-foreground">({finished.length})</span>
                </h2>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => clear.mutate()}
                  disabled={clear.isPending}
                >
                  <Trash2 aria-hidden />
                  Clear finished jobs
                </Button>
              </div>
              <p className="mb-3 text-xs text-muted-foreground">
                Clearing only tidies this list. It doesn't change or delete any files.
              </p>
              <ul className="flex flex-col gap-3">
                {finished.map((entry) => (
                  <EntryCard key={"job" in entry ? entry.job.id : entry.group.id} entry={entry} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}
