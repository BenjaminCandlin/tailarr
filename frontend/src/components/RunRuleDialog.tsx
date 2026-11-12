import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ListOrdered } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { RulePreviewList } from "@/components/RulePreviewList";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Rule } from "@/lib/api";
import { plural } from "@/lib/format";

/** "Run now": the preview first, then one job per file, as a group in the queue. */
export function RunRuleDialog({
  rule,
  open,
  onOpenChange,
}: {
  rule: Rule;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [started, setStarted] = useState<number | null>(null);
  const preview = useQuery({
    queryKey: ["rules", rule.id, "preview", rule.updated_at],
    queryFn: () => api.previewRule(rule),
    gcTime: 0,
  });
  const run = useMutation({
    mutationFn: () => api.runRule(rule.id),
    onSuccess: (data) => {
      setStarted(data.jobs);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["rules"] });
    },
  });
  const data = preview.data;
  const destructive = Boolean(data?.changes_originals);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={started === null ? `Run “${rule.name}” now?` : "Rule started"}
        description={started === null ? rule.sentence : undefined}
        className="md:max-w-2xl"
      >
        <DialogBody className="flex flex-col gap-4 text-sm">
          {started !== null ? (
            <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
              <CheckCircle2 className="size-10 text-success" aria-hidden />
              <p className="text-base font-medium">{plural(started, "job")} added to the queue</p>
            </div>
          ) : preview.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : preview.isError ? (
            <p role="alert" className="text-destructive">
              {preview.error.message}
            </p>
          ) : (
            data && <RulePreviewList preview={data} />
          )}
          {run.isError && (
            <p role="alert" className="rounded-lg bg-destructive-soft px-3 py-2 text-destructive">
              {run.error.message}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          {started === null ? (
            <>
              <Button variant="secondary" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                variant={destructive ? "destructive" : "primary"}
                onClick={() => run.mutate()}
                disabled={!data || data.will_run === 0 || !data.enough_space || run.isPending}
              >
                {run.isPending
                  ? "Starting…"
                  : data && data.will_run === 0
                    ? "Nothing to do"
                    : destructive
                      ? `Change ${plural(data?.will_run ?? 0, "original file")}`
                      : `Make ${plural(data?.will_run ?? 0, "copy", "copies")}`}
              </Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button asChild>
                <Link to="/queue">
                  <ListOrdered aria-hidden />
                  Open the Queue
                </Link>
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
