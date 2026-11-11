import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { useState } from "react";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { JobFollow } from "@/components/JobFollow";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Job, type ReplaceOriginalPreview } from "@/lib/api";
import { formatSize } from "@/lib/format";

function Summary({
  preview,
  understood,
  onUnderstood,
}: {
  preview: ReplaceOriginalPreview;
  understood: boolean;
  onUnderstood: (value: boolean) => void;
}) {
  const saved = preview.original_size - preview.copy_size;
  return (
    <>
      <div className="flex flex-col gap-2">
        <div className="rounded-lg border bg-muted/50 px-3 py-2">
          <p className="text-xs text-muted-foreground">The copy</p>
          <p className="font-medium [overflow-wrap:anywhere]" data-testid="replace-copy">
            {preview.copy_file}
          </p>
          <p className="text-xs text-muted-foreground">{formatSize(preview.copy_size)}</p>
        </div>
        <p className="px-1 text-muted-foreground">takes the place and the name of</p>
        <div className="rounded-lg border border-destructive/40 bg-destructive-soft/50 px-3 py-2">
          <p className="text-xs text-muted-foreground">Your original file</p>
          <p className="font-medium [overflow-wrap:anywhere]" data-testid="replace-original">
            {preview.original}
          </p>
          <p className="text-xs text-muted-foreground">{formatSize(preview.original_size)}</p>
        </div>
      </div>
      <p>
        The original isn't deleted straight away: it moves to a hidden recycle folder inside the
        film's folder and is deleted after{" "}
        <span className="font-medium">{preview.keep_days} days</span>. Until then you can get it
        back by moving it out of <span className="break-all">{preview.recycle_folder}</span>.
      </p>
      {!preview.hardlinked && saved > 0 && (
        <p className="text-muted-foreground">
          Once the recycle folder is emptied, this frees {formatSize(saved)}.
        </p>
      )}
      <p className="text-muted-foreground">
        Radarr and Plex keep finding the film under the same name. Plex may need a library refresh
        to notice the new tracks.
      </p>
      {preview.hardlinked && (
        <div className="flex gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3">
          <Link2 className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <div>
            <p className="font-medium">The original is also in your downloads</p>
            <p>
              It's still seeding. Seeding keeps working from the download copy, but the film then
              takes up twice the disk space until you remove the torrent from your download client.
            </p>
          </div>
        </div>
      )}
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border p-3 font-medium">
        <Checkbox
          checked={understood}
          onCheckedChange={(checked) => onUnderstood(checked === true)}
        />
        I understand my original file will be replaced by this copy
      </label>
    </>
  );
}

/**
 * "Replace the original with this copy": a strong confirmation, then the job's
 * progress inside the same dialog.
 */
export function ReplaceOriginalDialog({
  filmId,
  copyFile,
  open,
  onOpenChange,
  onReplaced,
}: {
  filmId: number;
  copyFile: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReplaced?: (job: Job) => void;
}) {
  const queryClient = useQueryClient();
  const [understood, setUnderstood] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [finished, setFinished] = useState<Job | null>(null);
  const preview = useQuery({
    queryKey: ["films", String(filmId), "replace-preview", copyFile],
    queryFn: () => api.previewReplaceOriginal(filmId, copyFile),
    enabled: open && jobId === null,
    retry: false,
    gcTime: 0,
  });
  const replace = useMutation({
    mutationFn: () => api.replaceOriginal(filmId, copyFile),
    onSuccess: (job) => {
      setJobId(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  function close(next: boolean) {
    if (!next) {
      // Refresh the film only now: the copy's row (and this dialog) may then disappear.
      if (finished) {
        void queryClient.invalidateQueries({ queryKey: ["films"] });
        if (finished.status === "done") onReplaced?.(finished);
      }
      setUnderstood(false);
      setJobId(null);
      setFinished(null);
      replace.reset();
    }
    onOpenChange(next);
  }

  if (jobId !== null) {
    return (
      <Dialog open={open} onOpenChange={close}>
        <DialogContent title="Replacing the original">
          <DialogBody>
            <JobFollow
              jobId={jobId}
              words={{
                running: "Replacing the original",
                done: "Original replaced",
                failed: "Couldn't replace the original",
                cancelled: "The original wasn't replaced",
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
      title="Replace the original with this copy?"
      description="Your original file will be swapped for the copy."
      confirmLabel="Replace the original"
      destructive
      onConfirm={() => replace.mutate()}
      confirmDisabled={!preview.data || !understood}
      pending={replace.isPending}
      error={
        preview.isError ? preview.error.message : replace.isError ? replace.error.message : null
      }
    >
      {preview.isPending ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : preview.data ? (
        <Summary preview={preview.data} understood={understood} onUnderstood={setUnderstood} />
      ) : null}
    </ConfirmSummary>
  );
}
