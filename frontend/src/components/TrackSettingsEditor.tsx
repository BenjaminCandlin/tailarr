import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Link2, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { ProgressBar } from "@/components/ProgressBar";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { TrackTable, type TrackEditing, type TrackValues } from "@/components/TrackTable";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, type Job, type Track, type TrackChange, type TrackSettingsPreview } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";
import { isActive, stepText, useJob } from "@/lib/jobs";

type Draft = Record<string, Partial<TrackValues>>;

function original(track: Track): TrackValues {
  return { default: track.default, forced: track.forced, name: track.name };
}

/** Only what differs from the file as it is now. */
export function changesFrom(tracks: Track[], draft: Draft): TrackChange[] {
  const changes: TrackChange[] = [];
  for (const track of tracks) {
    const wanted = draft[track.uid];
    if (!wanted) continue;
    const change: TrackChange = { uid: track.uid };
    if (wanted.default !== undefined && wanted.default !== track.default)
      change.default = wanted.default;
    if (wanted.forced !== undefined && wanted.forced !== track.forced)
      change.forced = wanted.forced;
    if (wanted.name !== undefined && wanted.name.trim() !== track.name)
      change.name = wanted.name.trim();
    if (Object.keys(change).length > 1) changes.push(change);
  }
  return changes;
}

/** Follows the job that's saving the changes, right where the owner made them. */
function JobProgress({ jobId, onFinished }: { jobId: number; onFinished: () => void }) {
  const job = useJob(jobId);
  const data = job.data;
  const finished = data !== undefined && !isActive(data);
  const told = useRef(false);
  useEffect(() => {
    if (finished && !told.current) {
      told.current = true;
      onFinished();
    }
  }, [finished, onFinished]);

  if (!data) {
    return (
      <div role="status" className="rounded-lg border bg-muted/50 px-4 py-3 text-sm">
        Starting…
      </div>
    );
  }
  if (isActive(data)) {
    return (
      <div role="status" className="flex flex-col gap-2 rounded-lg border bg-muted/50 px-4 py-3">
        <p className="text-sm font-medium">Saving track changes</p>
        <p className="text-sm text-muted-foreground">{stepText(data)}</p>
        <ProgressBar value={data.progress} label="Saving track changes" />
      </div>
    );
  }
  if (data.status === "done") {
    return (
      <div
        role="status"
        className="flex gap-3 rounded-lg border border-success/40 bg-success-soft px-4 py-3 text-sm"
      >
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
        <div>
          <p className="font-medium">Track changes saved</p>
          <p>{data.message}</p>
        </div>
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive-soft px-4 py-3 text-sm"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
      <div className="flex min-w-0 flex-col gap-2">
        <p className="font-medium">
          {data.status === "cancelled" ? "The changes weren't saved" : "Couldn't save the changes"}
        </p>
        <p>{data.error ?? data.message}</p>
        <TechnicalDetails details={data.error_details} />
        <p className="text-muted-foreground">
          Your choices are still on the page, so you can try again.{" "}
          <Link to="/queue" className="text-primary underline-offset-4 hover:underline">
            See the queue
          </Link>
        </p>
      </div>
    </div>
  );
}

function Summary({
  preview,
  understood,
  onUnderstood,
}: {
  preview: TrackSettingsPreview;
  understood: boolean;
  onUnderstood: (value: boolean) => void;
}) {
  return (
    <>
      <div className="rounded-lg border bg-muted/50 px-3 py-2">
        <p className="text-xs text-muted-foreground">File that will be changed</p>
        <p className="font-medium [overflow-wrap:anywhere]" data-testid="summary-file">
          {preview.file}
        </p>
      </div>
      <div>
        <p className="mb-2 font-medium">What will change</p>
        <ul className="flex flex-col gap-2" aria-label="What will change">
          {preview.tracks.map((track) => (
            <li key={track.uid} className="rounded-lg border px-3 py-2">
              <p className="font-medium">{track.label}</p>
              <ul className="list-disc pl-5 text-muted-foreground">
                {track.changes.map((change) => (
                  <li key={change}>{change}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-muted-foreground">
        Only the track settings are rewritten; the picture and sound aren't touched, so this takes a
        moment. No extra disk space is needed ({formatSize(preview.free_space)} free). Plex may need
        a library refresh afterwards to notice the change.
      </p>
      {preview.hardlinked && (
        <div className="flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning-soft p-3">
          <div className="flex gap-2">
            <Link2 className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <div>
              <p className="font-medium">This file is also in your downloads</p>
              <p>
                It's hardlinked, usually because it's still seeding in your download client.
                Changing it here also changes the seeding copy, which can break the torrent.
              </p>
            </div>
          </div>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium">
            <Checkbox
              checked={understood}
              onCheckedChange={(checked) => onUnderstood(checked === true)}
            />
            I understand: change it anyway, including the seeding copy
          </label>
        </div>
      )}
    </>
  );
}

/**
 * The track tables with Default/Forced switches and rename boxes, a "Save track changes"
 * bar, the summary to confirm, and the job's progress.
 */
export function TrackSettingsEditor({
  filmId,
  file,
  tracks,
}: {
  filmId: number;
  file: string;
  tracks: Track[];
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>({});
  const [preview, setPreview] = useState<TrackSettingsPreview | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);

  const changes = changesFrom(tracks, draft);

  const check = useMutation({
    mutationFn: () => api.previewTrackSettings(filmId, { file, changes }),
    onSuccess: (data) => {
      setUnderstood(false);
      setPreview(data);
    },
  });
  const save = useMutation({
    mutationFn: () =>
      api.changeTrackSettings(filmId, {
        file,
        changes,
        confirmed: true,
        allow_hardlinked: understood,
      }),
    onSuccess: (job) => {
      setPreview(null);
      setJobId(job.id);
      setRunning(true);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  function values(track: Track): TrackValues {
    return { ...original(track), ...draft[track.uid] };
  }

  const editing: TrackEditing = {
    values,
    changed: (track) => changes.some((c) => c.uid === track.uid),
    disabled: running,
    onChange: (track, change) => {
      setDraft((current) => {
        const next = { ...current, [track.uid]: { ...current[track.uid], ...change } };
        // One default per kind: players pick the first default they find, so having
        // two is confusing. Turning one on turns the others of that kind off.
        if (change.default) {
          for (const other of tracks) {
            const now = { ...original(other), ...current[other.uid] };
            if (other.type === track.type && other.uid !== track.uid && now.default) {
              next[other.uid] = { ...next[other.uid], default: false };
            }
          }
        }
        return next;
      });
    },
  };

  const onFinished = () => {
    setRunning(false);
    const job = queryClient.getQueryData<Job>(["jobs", jobId]);
    if (job?.status === "done") setDraft({});
    // Show the file as it is now (also in the film list and the film's file list).
    void queryClient.invalidateQueries({ queryKey: ["films"] });
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        To change which tracks play by default, which subtitles are forced, or a track's name, use
        the switches and pencil buttons below, then press{" "}
        <span className="font-medium text-foreground">Save track changes</span>. You'll see a
        summary before anything is changed.
      </p>
      <TrackTable tracks={tracks} editing={editing} />

      {jobId !== null && <JobProgress key={jobId} jobId={jobId} onFinished={onFinished} />}

      {changes.length > 0 && !running && (
        <div
          className="sticky bottom-20 z-10 flex flex-col gap-2 rounded-xl border border-primary/40 bg-card/95 p-3 shadow-lg backdrop-blur md:bottom-4 md:flex-row md:items-center"
          data-testid="save-bar"
        >
          <p className="flex-1 text-sm font-medium">
            {plural(changes.length, "track")} changed, not saved yet
            {check.isError && (
              <span role="alert" className="block font-normal text-destructive">
                {check.error.message}
              </span>
            )}
          </p>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                setDraft({});
                check.reset();
              }}
              className="flex-1 md:flex-none"
            >
              <Undo2 aria-hidden />
              Undo changes
            </Button>
            <Button
              onClick={() => check.mutate()}
              disabled={check.isPending}
              className="flex-1 md:flex-none"
            >
              {check.isPending ? "Checking…" : "Save track changes"}
            </Button>
          </div>
        </div>
      )}

      {preview && (
        <ConfirmSummary
          open
          onOpenChange={(open) => {
            if (!open) {
              setPreview(null);
              save.reset();
            }
          }}
          title="Change the original file?"
          description={`This changes the track settings inside the file itself. ${plural(
            preview.tracks.length,
            "track",
          )} will change.`}
          confirmLabel="Change the original file"
          destructive
          onConfirm={() => save.mutate()}
          confirmDisabled={preview.hardlinked && !understood}
          pending={save.isPending}
          error={save.isError ? save.error.message : null}
        >
          <Summary preview={preview} understood={understood} onUnderstood={setUnderstood} />
        </ConfirmSummary>
      )}
    </div>
  );
}
