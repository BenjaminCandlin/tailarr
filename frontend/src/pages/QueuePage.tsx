import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ListOrdered, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { JobCard } from "@/components/JobCard";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { FAST_POLL, SLOW_POLL, isActive } from "@/lib/jobs";

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

  const active = jobs.data.jobs.filter(isActive);
  const finished = jobs.data.jobs.filter((job) => !isActive(job));

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
                {active.map((job) => (
                  <JobCard key={job.id} job={job} />
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
                {finished.map((job) => (
                  <JobCard key={job.id} job={job} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}
