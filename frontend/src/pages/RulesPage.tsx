import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ListChecks, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { RunRuleDialog } from "@/components/RunRuleDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, type Rule, type RuleInput } from "@/lib/api";
import { timeAgo } from "@/lib/format";

const SCOPES: Record<Rule["scope"], string> = {
  films: "Films",
  tv: "TV",
  both: "Films and TV",
};

/** Starting points for the two rules the owner asked for. */
export const EXAMPLES: { label: string; rule: RuleInput }[] = [
  {
    label: "If a new film has Dolby Vision, make an HDR10 copy",
    rule: {
      name: "HDR10 copies of Dolby Vision films",
      enabled: false,
      scope: "films",
      conditions: [{ type: "has_dolby_vision", languages: [] }],
      action: { type: "hdr10_copy", overwrite: false },
      allow_originals: false,
      allow_hardlinked: false,
    },
  },
  {
    label: "Remove subtitle tracks that aren't English",
    rule: {
      name: "Only English subtitles",
      enabled: false,
      scope: "both",
      conditions: [{ type: "has_subtitles_not_in", languages: ["eng"] }],
      action: {
        type: "remove_tracks",
        audio: { mode: "all", languages: [] },
        subtitles: { mode: "only", languages: ["eng"] },
        remove_commentary: false,
        overwrite: false,
      },
      allow_originals: false,
      allow_hardlinked: false,
    },
  },
];

function RuleCard({ rule }: { rule: Rule }) {
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.setRuleEnabled(rule.id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules"] }),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteRule(rule.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules"] }),
  });
  return (
    <li
      className="flex flex-col gap-3 rounded-xl border bg-card p-4"
      aria-label={`Rule: ${rule.name}`}
      data-testid={`rule-${rule.id}`}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium [overflow-wrap:anywhere]">{rule.name}</h3>
            <Badge>{SCOPES[rule.scope]}</Badge>
            {rule.changes_originals && <Badge tone="danger">Changes originals</Badge>}
            {rule.enabled ? <Badge tone="success">On</Badge> : <Badge>Off</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{rule.sentence}</p>
          {rule.last_run_at && (
            <p className="mt-1 text-xs text-muted-foreground">
              Last run {timeAgo(rule.last_run_at)}
            </p>
          )}
        </div>
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => toggle.mutate(v)}
          aria-label={`${rule.enabled ? "Switch off" : "Switch on"} ${rule.name}`}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={() => setRunning(true)}>
          <Play aria-hidden />
          Preview and run now…
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link to={`/rules/${rule.id}`}>
            <Pencil aria-hidden />
            Edit
          </Link>
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDeleting(true)}>
          <Trash2 aria-hidden />
          Delete
        </Button>
      </div>
      {running && <RunRuleDialog rule={rule} open onOpenChange={setRunning} />}
      {deleting && (
        <ConfirmSummary
          open
          onOpenChange={setDeleting}
          title={`Delete the rule “${rule.name}”?`}
          confirmLabel="Delete the rule"
          destructive
          onConfirm={() => remove.mutate()}
          pending={remove.isPending}
          error={remove.isError ? remove.error.message : null}
        >
          <p>
            The rule stops working. Files it already made or changed stay as they are, and its
            history stays in the activity log.
          </p>
        </ConfirmSummary>
      )}
    </li>
  );
}

export function RulesPage() {
  const navigate = useNavigate();
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const description = "Changes Tailarr makes by itself when a new film or episode arrives.";
  return (
    <>
      <PageHeader
        title="Rules"
        description={description}
        actions={
          <Button onClick={() => navigate("/rules/new")}>
            <Plus aria-hidden />
            New rule
          </Button>
        }
      />
      {rules.isPending && <Skeleton className="h-32 w-full" />}
      {rules.isError && (
        <EmptyState icon={AlertTriangle} title="Couldn't load the rules">
          <p>{rules.error.message}</p>
        </EmptyState>
      )}
      {rules.data && rules.data.length === 0 && (
        <EmptyState icon={ListChecks} title="No rules yet">
          <p>
            A rule says what to do with new films or episodes, for example “If a new film has Dolby
            Vision, make an HDR10 copy”. New rules start switched off: preview them first to see
            exactly what they would do. Start from an example:
          </p>
          <div className="mt-4 flex flex-col items-center gap-2">
            {EXAMPLES.map((example, index) => (
              <Button
                key={example.label}
                variant="secondary"
                onClick={() => navigate(`/rules/new?example=${index}`)}
              >
                {example.label}
              </Button>
            ))}
          </div>
        </EmptyState>
      )}
      {rules.data && rules.data.length > 0 && (
        <>
          <p className="mb-4 text-sm text-muted-foreground">
            You can preview and run any rule on your whole library now. Rules that are{" "}
            <span className="font-medium text-foreground">on</span> will also run by themselves for
            new files once automatic triggers arrive (the next update). Original files are only
            changed by rules that say so.
          </p>
          <ul className="flex flex-col gap-3" aria-label="Rules">
            {rules.data.map((rule) => (
              <RuleCard key={rule.id} rule={rule} />
            ))}
          </ul>
        </>
      )}
    </>
  );
}
