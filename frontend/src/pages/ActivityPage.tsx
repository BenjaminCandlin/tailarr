import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, History } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusIcon } from "@/components/StatusIcon";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ActivityEntry } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { STATUS_LABELS } from "@/lib/jobs";

const FILTERS: { key: string; label: string; params: Parameters<typeof api.activity>[0] }[] = [
  { key: "all", label: "Everything", params: {} },
  { key: "rule", label: "Rules", params: { source: "rule" } },
  { key: "radarr", label: "Radarr", params: { source: "radarr" } },
  { key: "sonarr", label: "Sonarr", params: { source: "sonarr" } },
  { key: "plex", label: "Plex", params: { source: "plex" } },
  { key: "problems", label: "Problems only", params: { problems: true } },
];

const SOURCES: Record<string, string> = {
  rule: "Rule",
  radarr: "Radarr",
  sonarr: "Sonarr",
  plex: "Plex",
  tailarr: "Tailarr",
};

const JOB_TONES = {
  queued: "neutral",
  running: "accent",
  done: "success",
  failed: "danger",
  cancelled: "neutral",
  interrupted: "warning",
} as const;

function itemLink(entry: ActivityEntry): string | null {
  if (entry.film_id !== null) return `/films/${entry.film_id}`;
  if (entry.episode_id !== null) return `/tv/episodes/${entry.episode_id}`;
  return null;
}

function Entry({ entry }: { entry: ActivityEntry }) {
  const failed = entry.job_status === "failed" || entry.job_status === "interrupted";
  const link = itemLink(entry);
  return (
    <li className="flex gap-3 py-3 first:pt-0 last:pb-0" data-testid={`activity-${entry.id}`}>
      <StatusIcon status={entry.ok && !failed ? "ok" : "problem"} />
      <div className="min-w-0 flex-1 text-sm">
        <p className="[overflow-wrap:anywhere]">{entry.message}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span title={formatDate(entry.at)}>{timeAgo(entry.at)}</span>
          <Badge>{SOURCES[entry.source] ?? entry.source}</Badge>
          {entry.job_status && (
            <Badge tone={JOB_TONES[entry.job_status]}>Job: {STATUS_LABELS[entry.job_status]}</Badge>
          )}
          {entry.rule_name && entry.rule_id !== null && (
            <Link to={`/rules/${entry.rule_id}`} className="text-primary hover:underline">
              Rule “{entry.rule_name}”
            </Link>
          )}
          {link && (
            <Link to={link} className="text-primary hover:underline">
              Open the {entry.film_id !== null ? "film" : "episode"}
            </Link>
          )}
          {entry.job_id !== null && (
            <Link to="/queue" className="text-primary hover:underline">
              See the queue
            </Link>
          )}
        </div>
        {failed && entry.job_error && <p className="mt-1 text-destructive">{entry.job_error}</p>}
        <TechnicalDetails details={entry.details} />
      </div>
    </li>
  );
}

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((f) => f.key === params.get("show")) ?? FILTERS[0];
  const activity = useQuery({
    queryKey: ["activity", "page", filter.key],
    queryFn: () => api.activity({ limit: 200, ...filter.params }),
    refetchInterval: 10_000,
  });
  return (
    <>
      <Button asChild variant="ghost" className="-ml-3 mb-3">
        <Link to="/rules">
          <ArrowLeft aria-hidden />
          Rules
        </Link>
      </Button>
      <PageHeader
        title="Activity log"
        description="What Tailarr did by itself (rules), and what Radarr, Sonarr and Plex were told or said. Newest first."
        actions={
          <div className="flex items-center gap-2">
            <label htmlFor="activity-filter" className="text-sm font-medium">
              Show
            </label>
            <select
              id="activity-filter"
              value={filter.key}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                if (e.target.value === "all") next.delete("show");
                else next.set("show", e.target.value);
                setParams(next, { replace: true });
              }}
              className="h-11 cursor-pointer rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm"
            >
              {FILTERS.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        }
      />
      {activity.isPending && <Skeleton className="h-40 w-full" />}
      {activity.isError && (
        <EmptyState icon={AlertTriangle} title="Couldn't load the activity log">
          <p>{activity.error.message}</p>
        </EmptyState>
      )}
      {activity.data && activity.data.length === 0 && (
        <EmptyState icon={History} title="Nothing here yet">
          <p>
            When a rule runs, or Radarr, Sonarr or Plex are told about a change, it's written here.
          </p>
        </EmptyState>
      )}
      {activity.data && activity.data.length > 0 && (
        <ul className="divide-y rounded-xl border bg-card p-4" aria-label="Activity">
          {activity.data.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </>
  );
}
