import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileVideo, MonitorX } from "lucide-react";
import { useState } from "react";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { JobFollow } from "@/components/JobFollow";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, type ItemRef, type Hdr, type Hdr10CopyPreview, type Job } from "@/lib/api";
import { refreshLibrary } from "@/lib/jobs";
import { formatSize, plural } from "@/lib/format";

/**
 * Exactly what comes across into the copy, e.g. "Comes across: 2 audio tracks, 1 subtitle
 * track, 2 chapters, 1 attachment and the exact frame rate." Counts only the tracks that
 * are kept, so unticked tracks are never described as coming across.
 */
export function keptSentence(preview: Hdr10CopyPreview): string {
  const counts = preview.kept_counts ?? {};
  const parts: string[] = [];
  if (counts.video) parts.push(plural(counts.video, "other video track"));
  parts.push(plural(counts.audio ?? 0, "audio track"));
  parts.push(counts.subtitles ? plural(counts.subtitles, "subtitle track") : "no subtitle tracks");
  parts.push(plural(preview.chapters, "chapter"));
  parts.push(plural(preview.attachments, "attachment"));
  const lead = preview.removed.length
    ? "Comes across (everything except the tracks left out below)"
    : "Everything else comes across";
  return `${lead}: ${parts.join(", ")}, and the exact frame rate.`;
}

export function Hdr10Summary({
  preview,
  overwrite,
  onOverwrite,
}: {
  preview: Hdr10CopyPreview;
  overwrite: boolean;
  onOverwrite: (value: boolean) => void;
}) {
  const shows = preview.result.join(" and ") || "HDR10";
  // Tracks left out or changed: show exactly what the copy will have, unfolded.
  const changed = preview.removed.length > 0 || preview.settings.length > 0;
  return (
    <>
      <div className="rounded-lg border bg-muted/50 px-3 py-2">
        <p className="text-xs text-muted-foreground">New file</p>
        <p className="font-medium [overflow-wrap:anywhere]" data-testid="hdr10-new-file">
          {preview.new_file}
        </p>
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          Made from {preview.file}, in the same folder
        </p>
      </div>
      <div>
        <p className="mb-1 font-medium">What happens</p>
        <ul className="list-disc pl-5 text-muted-foreground" aria-label="What happens">
          <li>
            The Dolby Vision information (profile {preview.dv_profile}) is left out
            {preview.blu_ray_layers && ", together with the extra Blu-ray picture layer"}.
          </li>
          <li>
            The picture underneath is kept exactly as it is: nothing is re-encoded. Players without
            Dolby Vision show the copy as <span className="text-foreground">{shows}</span>.
          </li>
          <li data-testid="hdr10-kept">{keptSentence(preview)}</li>
          <li>Plex shows the copy as a second version of the film.</li>
        </ul>
      </div>
      {preview.removed.length > 0 && (
        <div>
          <p className="mb-1 font-medium">Also left out of the copy</p>
          <ul className="list-disc pl-5 text-muted-foreground" aria-label="Also left out">
            {preview.removed.map((line) => (
              <li key={line} className="[overflow-wrap:anywhere]">
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
      {preview.settings.length > 0 && (
        <div>
          <p className="mb-1 font-medium">Also changed in the copy</p>
          <ul className="flex flex-col gap-1" aria-label="Also changed in the copy">
            {preview.settings.map((item) => (
              <li key={item.label} className="text-muted-foreground">
                <span className="font-medium text-foreground">{item.label}:</span>{" "}
                {item.changes.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      {preview.warnings.map((warning) => (
        <p key={warning} className="rounded-lg bg-warning-soft px-3 py-2 text-warning">
          {warning}
        </p>
      ))}
      <details open={changed}>
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          Tracks in the copy
        </summary>
        <ul className="mt-2 list-disc pl-5 text-muted-foreground">
          <li>The video, without Dolby Vision</li>
          {preview.kept.map((line) => (
            <li key={line} className="[overflow-wrap:anywhere]">
              {line}
            </li>
          ))}
        </ul>
      </details>
      <div className="flex flex-col gap-1" data-testid="hdr10-space">
        {preview.space.map((need) => (
          <p
            key={need.label}
            className={need.enough ? "text-muted-foreground" : "font-medium text-destructive"}
          >
            {need.enough ? "Disk space" : "Not enough free space"} on {need.label}: needs up to{" "}
            {formatSize(need.needed)}, {formatSize(need.free)} free.
          </p>
        ))}
        <p className="text-muted-foreground">
          {preview.uses_work_folder
            ? "Working files go in the work folder and are removed afterwards."
            : "Working files are kept next to the film (hidden) and removed afterwards."}{" "}
          The whole film is read and written a few times, so a big film can take a while.
        </p>
      </div>
      {preview.exists && (
        <div className="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3">
          <p>
            <span className="font-medium">An HDR10 copy is already there.</span> It was made by
            Tailarr earlier.
          </p>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium">
            <Checkbox
              checked={overwrite}
              onCheckedChange={(checked) => onOverwrite(checked === true)}
            />
            Replace the existing copy
          </label>
        </div>
      )}
    </>
  );
}

/**
 * "Make a copy without Dolby Vision": for TVs and players that show Dolby Vision with
 * the wrong colours. Shown for files with Dolby Vision; explained (and not offered)
 * for profile 5, which has no HDR10 picture underneath.
 */
export function DolbyVisionAction({
  item,
  file,
  hdr,
  onOpenFile,
}: {
  item: ItemRef;
  file: string;
  hdr: Hdr;
  onOpenFile?: (name: string) => void;
}) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<Hdr10CopyPreview | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);

  const check = useMutation({
    mutationFn: () => api.previewHdr10Copy(item, file),
    onSuccess: (data) => {
      setOverwrite(false);
      setPreview(data);
    },
  });
  const start = useMutation({
    mutationFn: () => api.hdr10Copy(item, file, overwrite),
    onSuccess: (job) => {
      setPreview(null);
      setJobId(job.id);
      setRunning(true);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const onFinished = (job: Job) => {
    setRunning(false);
    if (job.status === "done") refreshLibrary(queryClient);
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };

  return (
    <section
      aria-labelledby="dv-action"
      className="flex flex-col gap-3 rounded-lg border p-4"
      data-testid="dv-action"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-3">
          <MonitorX className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
          <div>
            <h3 id="dv-action" className="font-medium">
              Make a copy without Dolby Vision
            </h3>
            <p className="text-sm text-muted-foreground">
              For TVs and players that show Dolby Vision with the wrong colours. Your original stays
              as it is.
            </p>
          </div>
        </div>
        {hdr.can_remove_dv && (
          <Button
            variant="secondary"
            onClick={() => check.mutate()}
            disabled={check.isPending || running}
            className="shrink-0"
          >
            {check.isPending ? "Checking…" : "Make an HDR10 copy…"}
          </Button>
        )}
      </div>
      {hdr.can_remove_dv && (
        <p className="text-sm text-muted-foreground">
          To change tracks in the same copy, untick or change them below and tick{" "}
          <span className="font-medium text-foreground">Also remove Dolby Vision</span> before
          saving: it's done in one go.
        </p>
      )}
      {!hdr.can_remove_dv && (
        <p className="text-sm text-muted-foreground" data-testid="dv-not-possible">
          Not possible for this file: Dolby Vision profile {hdr.dv_profile} has no HDR10 picture
          underneath, so without Dolby Vision the colours would be wrong.
        </p>
      )}
      {check.isError && (
        <p role="alert" className="text-sm text-destructive">
          {check.error.message}
        </p>
      )}
      {jobId !== null && (
        <JobFollow
          key={jobId}
          jobId={jobId}
          words={{
            running: "Making the HDR10 copy",
            done: "HDR10 copy saved",
            failed: "Couldn't make the HDR10 copy",
            cancelled: "The HDR10 copy wasn't made",
            afterFailure: "Your original wasn't changed.",
          }}
          onFinished={onFinished}
          doneExtra={(job) =>
            onOpenFile && job.result?.copy ? (
              <div>
                <Button variant="secondary" onClick={() => onOpenFile(job.result!.copy)}>
                  <FileVideo aria-hidden />
                  Show the copy
                </Button>
              </div>
            ) : null
          }
        />
      )}
      {preview && (
        <ConfirmSummary
          open
          onOpenChange={(open) => {
            if (!open) {
              setPreview(null);
              start.reset();
            }
          }}
          title="Make a copy without Dolby Vision?"
          description="A new HDR10 file is made next to the original. Your original isn't changed."
          confirmLabel="Make the HDR10 copy"
          onConfirm={() => start.mutate()}
          confirmDisabled={!preview.enough_space || (preview.exists && !overwrite)}
          pending={start.isPending}
          error={start.isError ? start.error.message : null}
        >
          <Hdr10Summary preview={preview} overwrite={overwrite} onOverwrite={setOverwrite} />
        </ConfirmSummary>
      )}
    </section>
  );
}
