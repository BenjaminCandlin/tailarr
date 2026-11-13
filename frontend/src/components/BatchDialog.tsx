import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Link2,
  ListOrdered,
  MinusCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import {
  ActionKindPicker,
  ActionOptions,
  START,
  Tick,
  actionOf,
  missingChoice,
  type Choices,
} from "@/components/ActionChoices";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { api, type BatchPreview, type BatchRequest, type BatchStarted } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Noun = { one: string; many: string };

const EPISODES: Noun = { one: "episode", many: "episodes" };

function PreviewSummary({
  preview,
  allowHardlinked,
  onAllowHardlinked,
  noun,
}: {
  preview: BatchPreview;
  allowHardlinked: boolean;
  onAllowHardlinked: (value: boolean) => void;
  noun: Noun;
}) {
  const running = preview.files.filter((f) => f.will_run);
  const skipped = preview.files.filter((f) => !f.will_run);
  const seeding = running.some((f) => f.hardlinked) || preview.hardlinked_skipped > 0;
  return (
    <>
      <div className="rounded-lg border bg-muted/50 px-3 py-2">
        <p className="font-medium">{preview.action}</p>
        <p className="text-muted-foreground">{preview.scope}</p>
      </div>
      <p data-testid="batch-counts">
        <span className="font-medium">{plural(preview.will_run, noun.one, noun.many)}</span> will{" "}
        {preview.changes_originals ? "be changed" : "get a copy"}
        {skipped.length > 0 && <>, {skipped.length} skipped</>}.
        {preview.flagged > 0 && (
          <span className="font-medium text-warning">
            {" "}
            {plural(preview.flagged, "file")} flagged: see below.
          </span>
        )}
      </p>
      {preview.copies > 0 && !preview.files.some((f) => f.is_copy) && (
        <p className="text-muted-foreground">
          These {noun.many} also have {plural(preview.copies, "copy", "copies")} made by Tailarr,
          which are left as they are. Go back and tick “Also change the copies” to change them too.
        </p>
      )}
      {preview.changes_originals && running.length > 0 && (
        <div className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3 text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            This changes the original files listed below (only their track settings: the picture and
            sound aren't touched). Plex may need a library refresh afterwards.
          </p>
        </div>
      )}
      {preview.changes_originals && seeding && (
        <div className="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3">
          <div className="flex gap-2">
            <Link2 className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <p>
              Some {noun.many} are also in your downloads (still seeding). Changing them also
              changes the seeding copy, which can break the torrent, so they're skipped unless you
              tick this.
            </p>
          </div>
          <Tick checked={allowHardlinked} onChange={onAllowHardlinked}>
            I understand: change seeding {noun.many} too
          </Tick>
        </div>
      )}
      {running.length > 0 && (
        <div>
          <p className="mb-2 font-medium">
            {preview.changes_originals ? "Will be changed" : "Copies to make"}
          </p>
          <ul
            className="flex flex-col gap-1.5"
            aria-label={`${noun.many[0].toUpperCase()}${noun.many.slice(1)} that will change`}
          >
            {running.map((file) => (
              <li key={`${file.item_id}-${file.file}`} className="rounded-lg border px-3 py-2">
                <p className="font-medium [overflow-wrap:anywhere]">{file.label}</p>
                {file.new_file && (
                  <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
                    New file: {file.new_file}
                  </p>
                )}
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {file.lines.map((line) => (
                    <li key={line} className="[overflow-wrap:anywhere]">
                      {line}
                    </li>
                  ))}
                </ul>
                {file.warnings.map((warning) => (
                  <p
                    key={warning}
                    className="mt-1 flex gap-1.5 font-medium text-warning"
                    data-testid="batch-warning"
                  >
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
                    {warning}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
      {skipped.length > 0 && (
        <details
          className="rounded-lg border px-3 py-2"
          open={running.length === 0 || skipped.some((f) => f.warnings.length > 0)}
        >
          <summary className="min-h-9 cursor-pointer py-1 font-medium">
            Skipped ({skipped.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-2" aria-label={`Skipped ${noun.many}`}>
            {skipped.map((file) => (
              <li key={`${file.item_id}-${file.file}`} className="flex gap-2">
                <MinusCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="[overflow-wrap:anywhere]">
                  <span className="font-medium">{file.label}</span>
                  <span
                    className={
                      file.warnings.length ? "font-medium text-warning" : "text-muted-foreground"
                    }
                  >
                    {" "}
                    – {file.reason}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {preview.space.length > 0 && (
        <div className="flex flex-col gap-1">
          {preview.space.map((space) => (
            <p key={space.label} className={cn(!space.enough && "font-medium text-destructive")}>
              Space needed on {space.label}: {formatSize(space.needed)} ({formatSize(space.free)}{" "}
              free)
              {!space.enough && ". Not enough: free up some space or choose fewer at a time."}
            </p>
          ))}
          <p className="text-xs text-muted-foreground">
            Jobs run one at a time, and each one checks the free space again before it starts.
          </p>
        </div>
      )}
    </>
  );
}

type Step = "choose" | "preview" | "started";

export { actionOf, missingChoice };

/** What to change: a TV season or show, or a selection of films. */
export type BatchTarget =
  { kind: "show"; showId: number; season: number | null } | { kind: "films"; filmIds: number[] };

/**
 * Apply one action to many films or episodes (a season, a whole show, or chosen films).
 * Track numbers differ from file to file, so choices are made by language ("keep only
 * English subtitles"), and the summary shows what that means for each file before
 * anything starts. One job per file, shown as a group in the queue.
 */
export function BatchDialog({
  target,
  scopeLabel,
  hasCopies = false,
  open,
  onOpenChange,
}: {
  target: BatchTarget;
  scopeLabel: string;
  /** Some of these items have copies Tailarr made: offer (and pre-tick) changing them. */
  hasCopies?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const noun: Noun = target.kind === "films" ? { one: "film", many: "films" } : EPISODES;
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("choose");
  const [choices, setChoices] = useState<Choices>(START);
  const [allowHardlinked, setAllowHardlinked] = useState(false);
  const [includeCopies, setIncludeCopies] = useState(hasCopies);
  const [started, setStarted] = useState<BatchStarted | null>(null);

  // Plain HDR10 copies don't touch copies (they're already without Dolby Vision); with
  // track changes, or for the other actions, existing copies can be brought in line.
  const copiesMatter = hasCopies && (choices.kind !== "hdr10_copy" || choices.hdr10Tracks);
  const request = (allow = allowHardlinked): BatchRequest => ({
    action: actionOf(choices),
    allow_hardlinked: allow,
    include_copies: copiesMatter && includeCopies,
  });
  const preview = useMutation({
    mutationFn: (allow: boolean) =>
      target.kind === "films"
        ? api.previewFilmsBatch(target.filmIds, request(allow))
        : api.previewBatch(target.showId, { ...request(allow), season: target.season }),
    onSuccess: () => setStep("preview"),
  });
  const start = useMutation({
    mutationFn: () =>
      target.kind === "films"
        ? api.startFilmsBatch(target.filmIds, request())
        : api.startBatch(target.showId, { ...request(), season: target.season }),
    onSuccess: (data) => {
      setStarted(data);
      setStep("started");
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const set = (change: Partial<Choices>) => {
    setChoices((current) => ({ ...current, ...change }));
    preview.reset();
  };
  const missing = missingChoice(choices);
  const data = preview.data;
  const destructive = Boolean(data?.changes_originals);

  let body: ReactNode;
  let footer: ReactNode;
  if (step === "choose") {
    body = (
      <>
        <ActionKindPicker
          value={choices.kind}
          onChange={(kind) => set({ kind })}
          name="batch-kind"
          noun={noun}
        />
        <div className="rounded-xl border p-3">
          <ActionOptions choices={choices} set={set} />
        </div>
        {copiesMatter && (
          <div className="rounded-xl border p-3">
            <Tick
              checked={includeCopies}
              onChange={(value) => {
                setIncludeCopies(value);
                preview.reset();
              }}
            >
              Also change the copies Tailarr made of these {noun.many}, not just the originals
            </Tick>
            <p className="pl-8 text-xs text-muted-foreground">
              Some of these {noun.many} have copies (for example HDR10 copies). Their tracks are
              changed too, so both versions match. Copies are updated where they are (no copy of a
              copy is made).
            </p>
          </div>
        )}
        {missing && <p className="text-muted-foreground">{missing}</p>}
      </>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button
          onClick={() => preview.mutate(allowHardlinked)}
          disabled={Boolean(missing) || preview.isPending}
        >
          {preview.isPending ? `Checking every ${noun.one}…` : "Show what will happen"}
        </Button>
      </>
    );
  } else if (step === "preview" && data) {
    body = (
      <PreviewSummary
        preview={data}
        noun={noun}
        allowHardlinked={allowHardlinked}
        onAllowHardlinked={(value) => {
          setAllowHardlinked(value);
          preview.mutate(value);
        }}
      />
    );
    footer = (
      <>
        <Button variant="ghost" onClick={() => setStep("choose")}>
          <ArrowLeft aria-hidden />
          Back
        </Button>
        <Button
          variant={destructive ? "destructive" : "primary"}
          onClick={() => start.mutate()}
          disabled={
            data.will_run === 0 || !data.enough_space || start.isPending || preview.isPending
          }
        >
          {start.isPending
            ? "Starting…"
            : destructive
              ? `Change ${plural(data.will_run, "original file")}`
              : `Make ${plural(data.will_run, "copy", "copies")}`}
        </Button>
      </>
    );
  } else {
    body = (
      <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
        <CheckCircle2 className="size-10 text-success" aria-hidden />
        <p className="text-base font-medium">
          {plural(started?.jobs ?? 0, "job")} added to the queue
        </p>
        <p className="text-muted-foreground">
          They run one at a time and are shown together on the Queue page, where you can follow them
          or cancel the rest.
        </p>
      </div>
    );
    footer = (
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
    );
  }

  const error = (step === "choose" ? preview.error : (start.error ?? preview.error))?.message;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={step === "preview" ? "Check before starting" : `Change ${scopeLabel}`}
        description={
          step === "choose"
            ? `Choose what to do to every ${noun.one}. You'll see exactly what happens to each one before anything starts.`
            : undefined
        }
        className="md:max-w-2xl"
      >
        <DialogBody className="flex flex-col gap-4 text-sm">
          {body}
          {error && (
            <p role="alert" className="rounded-lg bg-destructive-soft px-3 py-2 text-destructive">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>{footer}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
