import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Link2 } from "lucide-react";
import { useState } from "react";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { JobFollow } from "@/components/JobFollow";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ItemRef, type Job, type ReplaceOriginalPreview } from "@/lib/api";
import { refreshLibrary } from "@/lib/jobs";
import { formatSize } from "@/lib/format";

/** What happens to disk space, in plain words. */
export function spaceText(preview: ReplaceOriginalPreview): string {
  const together = formatSize(preview.original_size + preview.copy_size);
  const saved = preview.original_size - preview.copy_size;
  const smaller =
    saved > 0
      ? ` The copy is ${formatSize(saved)} smaller than the original, because ${
          preview.loses_dolby_vision
            ? "the Dolby Vision information is left out"
            : "of the tracks you left out"
        }.`
      : "";
  if (preview.hardlinked) {
    return (
      `Right now the original and the copy take up ${together} together. Because the original ` +
      `is still seeding, its ${formatSize(preview.original_size)} is only freed once the recycle ` +
      `folder is emptied and the torrent is removed.${smaller}`
    );
  }
  return (
    `Right now the original and the copy take up ${together} together. When the recycle ` +
    `folder is emptied, the original's ${formatSize(preview.original_size)} is freed, leaving ` +
    `just the copy.${smaller}`
  );
}

function Summary({
  preview,
  understood,
  onUnderstood,
}: {
  preview: ReplaceOriginalPreview;
  understood: boolean;
  onUnderstood: (value: boolean) => void;
}) {
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
      {preview.loses_dolby_vision && (
        <div
          className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3"
          data-testid="loses-dolby-vision"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <div>
            <p className="font-medium">Dolby Vision will be gone from this film</p>
            <p>
              This is an HDR10 copy, so after replacing, the film only has HDR10. TVs that play
              Dolby Vision properly will no longer get it. Most people keep both versions side by
              side instead: Plex lets each device play the one that suits it.
            </p>
            {preview.may_redownload && (
              <p className="mt-2" data-testid="may-redownload">
                {preview.may_redownload} is connected: if its quality settings prefer Dolby Vision
                (for example TRaSH Guides custom formats), {preview.may_redownload} may see that
                Dolby Vision is gone and download a Dolby Vision release again as an “upgrade”.
              </p>
            )}
          </div>
        </div>
      )}
      <p>
        The original isn't deleted straight away: it moves to a hidden recycle folder inside the
        film's folder and is deleted after{" "}
        <span className="font-medium">{preview.keep_days} days</span>. Until then you can get it
        back by moving it out of <span className="break-all">{preview.recycle_folder}</span>.
      </p>
      <p className="text-muted-foreground" data-testid="replace-space">
        {spaceText(preview)}
      </p>
      <p className="text-muted-foreground">
        Radarr and Plex keep finding the film under the same name. Plex may need a library refresh
        to notice the change.
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
        {preview.loses_dolby_vision
          ? "I understand my original will be replaced and Dolby Vision will be gone"
          : "I understand my original file will be replaced by this copy"}
      </label>
    </>
  );
}

/**
 * "Replace the original with this copy": a strong confirmation, then the job's
 * progress inside the same dialog.
 */
export function ReplaceOriginalDialog({
  item,
  copyFile,
  open,
  onOpenChange,
  onReplaced,
}: {
  item: ItemRef;
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
    queryKey: [item.kind, String(item.id), "replace-preview", copyFile],
    queryFn: () => api.previewReplaceOriginal(item, copyFile),
    enabled: open && jobId === null,
    retry: false,
    gcTime: 0,
  });
  const replace = useMutation({
    mutationFn: () => api.replaceOriginal(item, copyFile),
    onSuccess: (job) => {
      setJobId(job.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  function close(next: boolean) {
    if (!next) {
      // Refresh the film only now: the copy's row (and this dialog) may then disappear.
      if (finished) {
        refreshLibrary(queryClient);
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
