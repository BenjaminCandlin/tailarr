import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { JobFollow } from "@/components/JobFollow";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { api, type Job, type RecycledFile } from "@/lib/api";
import { formatSize } from "@/lib/format";
import { refreshLibrary } from "@/lib/jobs";

function folderOf(path: string): string {
  return path.slice(0, path.lastIndexOf("/")) || "/";
}

/**
 * "Restore" for a file in the recycle folder: a summary to confirm (with a "swap them"
 * choice when a file with that name is there now), then the job's progress.
 */
export function RestoreDialog({
  file,
  keepDays,
  open,
  onOpenChange,
}: {
  file: RecycledFile;
  keepDays: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [swap, setSwap] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [finished, setFinished] = useState<Job | null>(null);
  const restore = useMutation({
    mutationFn: () => api.restoreRecycled(file.id, file.clash && swap),
    onSuccess: (job) => {
      setJobId(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  function close(next: boolean) {
    if (!next) {
      if (finished) {
        refreshLibrary(queryClient);
        void queryClient.invalidateQueries({ queryKey: ["settings", "recycle"] });
      }
      setSwap(false);
      setJobId(null);
      setFinished(null);
      restore.reset();
    }
    onOpenChange(next);
  }

  if (jobId !== null) {
    return (
      <Dialog open={open} onOpenChange={close}>
        <DialogContent title="Putting the file back">
          <DialogBody>
            <JobFollow
              jobId={jobId}
              words={{
                running: "Putting the file back",
                done: "File put back",
                failed: "Couldn't put the file back",
                cancelled: "The file wasn't put back",
              }}
              onFinished={(job) => {
                setFinished(job);
                void queryClient.invalidateQueries({ queryKey: ["jobs"] });
              }}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => close(false)} disabled={!finished}>
              {finished ? "Close" : "Please wait…"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <ConfirmSummary
      open={open}
      onOpenChange={close}
      title="Put this file back?"
      description="It goes back to where it was, with its own name."
      confirmLabel={file.clash ? "Swap them" : "Put it back"}
      destructive={file.clash}
      onConfirm={() => restore.mutate()}
      confirmDisabled={file.clash && !swap}
      pending={restore.isPending}
      error={restore.isError ? restore.error.message : null}
    >
      <div className="rounded-lg border bg-muted/50 px-3 py-2">
        <p className="text-xs text-muted-foreground">From the recycle folder</p>
        <p className="font-medium [overflow-wrap:anywhere]" data-testid="restore-file">
          {file.name}
        </p>
        <p className="text-xs text-muted-foreground">{formatSize(file.size)}</p>
      </div>
      <p>
        It goes back into{" "}
        <span className="[overflow-wrap:anywhere]">{folderOf(file.original_path)}</span>. This is an
        instant rename on the same disk: nothing is copied.
      </p>
      {file.clash ? (
        <div
          className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3"
          data-testid="restore-clash"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <div className="flex flex-col gap-2">
            <p className="font-medium">A file with this name is there now</p>
            <p>
              “<span className="[overflow-wrap:anywhere]">{file.name}</span>”
              {file.clash_size !== null && ` (${formatSize(file.clash_size)})`} is in that folder
              now, probably the copy that replaced it. To put the old file back, the current one
              moves to the recycle folder first (kept {keepDays} days), so you can swap back later.
            </p>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border bg-background p-3 font-medium">
              <Checkbox checked={swap} onCheckedChange={(checked) => setSwap(checked === true)} />
              Swap them: move the current file to the recycle folder
            </label>
          </div>
        </div>
      ) : null}
      <p className="text-muted-foreground">
        Plex, Radarr and Sonarr see the file again after their next library scan, or straight away
        if they're connected in Settings.
      </p>
    </ConfirmSummary>
  );
}
