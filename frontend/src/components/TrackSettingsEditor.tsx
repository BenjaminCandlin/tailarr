import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, FileVideo, Link2, Undo2 } from "lucide-react";
import { useState } from "react";

import { ConfirmSummary } from "@/components/ConfirmSummary";
import { CopySummary } from "@/components/CopySummary";
import { JobFollow, type JobWords } from "@/components/JobFollow";
import { ReplaceOriginalDialog } from "@/components/ReplaceOriginalDialog";
import { TrackTable, type TrackEditing, type TrackValues } from "@/components/TrackTable";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  api,
  type ItemRef,
  type Job,
  type RemoveTracksPreview,
  type Track,
  type TrackChange,
  type TrackSettingsPreview,
} from "@/lib/api";
import { refreshLibrary } from "@/lib/jobs";
import { formatSize, plural } from "@/lib/format";

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

function SettingsSummary({
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

const SETTINGS_WORDS: JobWords = {
  running: "Saving track changes",
  done: "Track changes saved",
  failed: "Couldn't save the changes",
  cancelled: "The changes weren't saved",
  afterFailure: "Your choices are still on the page, so you can try again.",
};

const COPY_WORDS: JobWords = {
  running: "Making the copy",
  done: "Copy saved",
  failed: "Couldn't make the copy",
  cancelled: "The copy wasn't made",
  afterFailure: "Your original wasn't changed, and your choices are still on the page.",
};

type Started = { id: number; kind: "settings" | "copy" };

/**
 * The track tables with Keep ticks, Default/Forced switches and rename buttons, and a
 * save bar. With every track ticked, "Save track changes" changes the file itself. With
 * some unticked, "Save a copy without the unticked tracks" makes a new file instead (with
 * any setting changes applied to the copy) and leaves the original alone.
 */
export function TrackSettingsEditor({
  item,
  file,
  tracks,
  onOpenFile,
}: {
  item: ItemRef;
  file: string;
  tracks: Track[];
  /** Show another of the film's files (e.g. the new copy). */
  onOpenFile?: (name: string) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>({});
  const [removed, setRemoved] = useState<string[]>([]);
  const [settingsPreview, setSettingsPreview] = useState<TrackSettingsPreview | null>(null);
  const [copyPreview, setCopyPreview] = useState<RemoveTracksPreview | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [started, setStarted] = useState<Started | null>(null);
  const [running, setRunning] = useState(false);
  const [replacing, setReplacing] = useState<string | null>(null);

  const copyMode = removed.length > 0;
  const changes = changesFrom(tracks, draft).filter((c) => !removed.includes(c.uid));

  const checkSettings = useMutation({
    mutationFn: () => api.previewTrackSettings(item, { file, changes }),
    onSuccess: (data) => {
      setUnderstood(false);
      setSettingsPreview(data);
    },
  });
  const checkCopy = useMutation({
    mutationFn: () => api.previewRemoveTracks(item, { file, remove: removed, changes }),
    onSuccess: (data) => {
      setOverwrite(data.updates_copy);
      setCopyPreview(data);
    },
  });
  const check = copyMode ? checkCopy : checkSettings;

  function begin(job: Job, kind: Started["kind"]) {
    setSettingsPreview(null);
    setCopyPreview(null);
    setStarted({ id: job.id, kind });
    setRunning(true);
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }
  const saveSettings = useMutation({
    mutationFn: () =>
      api.changeTrackSettings(item, {
        file,
        changes,
        confirmed: true,
        allow_hardlinked: understood,
      }),
    onSuccess: (job) => begin(job, "settings"),
  });
  const saveCopy = useMutation({
    mutationFn: () =>
      api.removeTracks(item, { file, remove: removed, changes, confirmed: true, overwrite }),
    onSuccess: (job) => begin(job, "copy"),
  });

  function values(track: Track): TrackValues {
    return { ...original(track), ...draft[track.uid] };
  }

  const editing: TrackEditing = {
    values,
    changed: (track) => changes.some((c) => c.uid === track.uid),
    kept: (track) => !removed.includes(track.uid),
    onKeep: (track, keep) => {
      setRemoved((current) =>
        keep ? current.filter((uid) => uid !== track.uid) : [...current, track.uid],
      );
      checkSettings.reset();
      checkCopy.reset();
    },
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

  const onFinished = (job: Job) => {
    setRunning(false);
    if (job.status === "done") {
      setDraft({});
      setRemoved([]);
    }
    // Show the file(s) as they are now (also in the film list and the film's file list).
    refreshLibrary(queryClient);
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };

  const pending = changes.length > 0 || copyMode;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Change settings:</span> use the switches and
          pencil buttons to choose default and forced tracks or rename them, then press{" "}
          <span className="font-medium text-foreground">Save track changes</span>.
        </p>
        <p>
          <span className="font-medium text-foreground">Remove tracks:</span> untick the audio or
          subtitle tracks you don't want, then press{" "}
          <span className="font-medium text-foreground">
            Save a copy without the unticked tracks
          </span>
          . Your original stays as it is.
        </p>
        <p>You'll always see a summary before anything happens.</p>
      </div>
      <TrackTable tracks={tracks} editing={editing} />

      {started !== null && (
        <JobFollow
          key={started.id}
          jobId={started.id}
          words={started.kind === "copy" ? COPY_WORDS : SETTINGS_WORDS}
          onFinished={onFinished}
          doneExtra={(job) =>
            started.kind === "copy" && job.result?.copy ? (
              <div className="flex flex-col gap-2 sm:flex-row">
                {onOpenFile && job.result.copy !== file && (
                  <Button variant="secondary" onClick={() => onOpenFile(job.result!.copy)}>
                    <FileVideo aria-hidden />
                    Show the copy
                  </Button>
                )}
                <Button variant="secondary" onClick={() => setReplacing(job.result!.copy)}>
                  Replace the original with this copy…
                </Button>
              </div>
            ) : null
          }
        />
      )}

      {pending && !running && (
        <div
          className="sticky bottom-20 z-10 flex flex-col gap-2 rounded-xl border border-primary/40 bg-card/95 p-3 shadow-lg backdrop-blur md:bottom-4 md:flex-row md:items-center"
          data-testid="save-bar"
        >
          <div className="flex-1 text-sm">
            <p className="font-medium">
              {copyMode
                ? [
                    `${plural(removed.length, "track")} left out`,
                    changes.length > 0 && `${plural(changes.length, "track")} changed`,
                  ]
                    .filter(Boolean)
                    .join(", ")
                : `${plural(changes.length, "track")} changed, not saved yet`}
            </p>
            {copyMode && (
              <p className="text-muted-foreground">
                Saved as a new copy next to the original. Your original stays as it is.
              </p>
            )}
            {check.isError && (
              <p role="alert" className="text-destructive">
                {check.error.message}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              variant="ghost"
              onClick={() => {
                setDraft({});
                setRemoved([]);
                checkSettings.reset();
                checkCopy.reset();
              }}
            >
              <Undo2 aria-hidden />
              Undo changes
            </Button>
            <Button onClick={() => check.mutate()} disabled={check.isPending}>
              {copyMode && <Copy aria-hidden />}
              {check.isPending
                ? "Checking…"
                : copyMode
                  ? "Save a copy without the unticked tracks"
                  : "Save track changes"}
            </Button>
          </div>
        </div>
      )}

      {settingsPreview && (
        <ConfirmSummary
          open
          onOpenChange={(open) => {
            if (!open) {
              setSettingsPreview(null);
              saveSettings.reset();
            }
          }}
          title="Change the original file?"
          description={`This changes the track settings inside the file itself. ${plural(
            settingsPreview.tracks.length,
            "track",
          )} will change.`}
          confirmLabel="Change the original file"
          destructive
          onConfirm={() => saveSettings.mutate()}
          confirmDisabled={settingsPreview.hardlinked && !understood}
          pending={saveSettings.isPending}
          error={saveSettings.isError ? saveSettings.error.message : null}
        >
          <SettingsSummary
            preview={settingsPreview}
            understood={understood}
            onUnderstood={setUnderstood}
          />
        </ConfirmSummary>
      )}

      {copyPreview && (
        <ConfirmSummary
          open
          onOpenChange={(open) => {
            if (!open) {
              setCopyPreview(null);
              saveCopy.reset();
            }
          }}
          title={
            copyPreview.updates_copy ? "Update this copy?" : "Make a copy without these tracks?"
          }
          description={
            copyPreview.updates_copy
              ? "This is a copy Tailarr made, so it's updated. Your original isn't touched."
              : "A new file is made next to the original. Your original isn't changed."
          }
          confirmLabel={copyPreview.updates_copy ? "Update the copy" : "Make the copy"}
          onConfirm={() => saveCopy.mutate()}
          confirmDisabled={
            !copyPreview.enough_space ||
            (copyPreview.exists && !copyPreview.updates_copy && !overwrite)
          }
          pending={saveCopy.isPending}
          error={saveCopy.isError ? saveCopy.error.message : null}
        >
          <CopySummary preview={copyPreview} overwrite={overwrite} onOverwrite={setOverwrite} />
        </ConfirmSummary>
      )}

      {replacing && (
        <ReplaceOriginalDialog
          item={item}
          copyFile={replacing}
          open
          onOpenChange={(open) => !open && setReplacing(null)}
        />
      )}
    </div>
  );
}
