import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  Link2,
  ListOrdered,
  MinusCircle,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { LanguagePicker, LanguageSelect } from "@/components/LanguagePicker";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  api,
  type BatchAction,
  type BatchPreview,
  type BatchRequest,
  type BatchStarted,
} from "@/lib/api";
import { formatSize, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = BatchAction["type"];

const KINDS: { kind: Kind; icon: LucideIcon; title: string; text: string }[] = [
  {
    kind: "hdr10_copy",
    icon: Sparkles,
    title: "Make copies without Dolby Vision",
    text: "For episodes with Dolby Vision, an HDR10 copy is made next to each one. For TVs and players that show Dolby Vision with the wrong colours. Your originals stay as they are.",
  },
  {
    kind: "remove_tracks",
    icon: Copy,
    title: "Save copies without some tracks",
    text: "Choose which languages to keep. Each episode gets a copy without the other audio or subtitle tracks. Your originals stay as they are.",
  },
  {
    kind: "default_tracks",
    icon: SlidersHorizontal,
    title: "Choose the default audio and subtitles",
    text: "Sets which audio and subtitles players pick by themselves. This changes the original files (only their settings, quickly).",
  },
];

type Choices = {
  kind: Kind;
  overwrite: boolean;
  audioMode: "all" | "only";
  audioLanguages: string[];
  subtitleMode: "all" | "only" | "none";
  subtitleLanguages: string[];
  removeCommentary: boolean;
  defaultAudio: string | null;
  defaultSubtitles: "keep" | "off" | "language";
  defaultSubtitleLanguage: string | null;
};

const START: Choices = {
  kind: "hdr10_copy",
  overwrite: false,
  audioMode: "all",
  audioLanguages: ["eng"],
  subtitleMode: "only",
  subtitleLanguages: ["eng"],
  removeCommentary: false,
  defaultAudio: null,
  defaultSubtitles: "keep",
  defaultSubtitleLanguage: null,
};

export function actionOf(c: Choices): BatchAction {
  if (c.kind === "hdr10_copy") return { type: "hdr10_copy", overwrite: c.overwrite };
  if (c.kind === "remove_tracks") {
    return {
      type: "remove_tracks",
      audio: { mode: c.audioMode, languages: c.audioMode === "only" ? c.audioLanguages : [] },
      subtitles: {
        mode: c.subtitleMode,
        languages: c.subtitleMode === "only" ? c.subtitleLanguages : [],
      },
      remove_commentary: c.removeCommentary,
      overwrite: c.overwrite,
    };
  }
  return {
    type: "default_tracks",
    audio_language: c.defaultAudio,
    subtitles: c.defaultSubtitles,
    subtitle_language: c.defaultSubtitles === "language" ? c.defaultSubtitleLanguage : null,
  };
}

/** Why the choices can't be checked yet, in plain words (or null when they're complete). */
export function missingChoice(c: Choices): string | null {
  if (c.kind === "remove_tracks") {
    if (c.audioMode === "all" && c.subtitleMode === "all" && !c.removeCommentary)
      return "Choose which audio or subtitle tracks to remove.";
    if (c.audioMode === "only" && c.audioLanguages.length === 0)
      return "Choose at least one audio language to keep.";
    if (c.subtitleMode === "only" && c.subtitleLanguages.length === 0)
      return "Choose at least one subtitle language to keep.";
  }
  if (c.kind === "default_tracks") {
    if (!c.defaultAudio && c.defaultSubtitles === "keep")
      return "Choose a default audio language or default subtitles.";
    if (c.defaultSubtitles === "language" && !c.defaultSubtitleLanguage)
      return "Choose the subtitle language to show by default.";
  }
  return null;
}

function Radio({
  name,
  checked,
  onChange,
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  children: ReactNode;
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3">
      <input
        type="radio"
        name={name}
        checked={checked}
        onChange={onChange}
        className="size-5 shrink-0 cursor-pointer accent-primary"
      />
      <span>{children}</span>
    </label>
  );
}

function Tick({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center gap-3">
      <Checkbox checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <span>{children}</span>
    </label>
  );
}

function Options({ choices, set }: { choices: Choices; set: (c: Partial<Choices>) => void }) {
  if (choices.kind === "hdr10_copy") {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground">
          Episodes without Dolby Vision are skipped, and so are Dolby Vision profile 5 episodes
          (they have no HDR10 picture underneath, so the colours would be wrong).
        </p>
        <Tick checked={choices.overwrite} onChange={(v) => set({ overwrite: v })}>
          Replace HDR10 copies Tailarr made before
        </Tick>
      </div>
    );
  }
  if (choices.kind === "remove_tracks") {
    return (
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 font-medium">Audio</legend>
          <Radio
            name="audio"
            checked={choices.audioMode === "all"}
            onChange={() => set({ audioMode: "all" })}
          >
            Keep all audio tracks
          </Radio>
          <Radio
            name="audio"
            checked={choices.audioMode === "only"}
            onChange={() => set({ audioMode: "only" })}
          >
            Keep only these languages
          </Radio>
          {choices.audioMode === "only" && (
            <div className="pl-8">
              <LanguagePicker
                id="batch-audio-languages"
                label="Add an audio language to keep"
                value={choices.audioLanguages}
                onChange={(codes) => set({ audioLanguages: codes })}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Tracks with no language set, and tracks marked as the original language, are kept
                too. An episode is skipped if it would be left with no sound.
              </p>
            </div>
          )}
        </fieldset>
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 font-medium">Subtitles</legend>
          <Radio
            name="subs"
            checked={choices.subtitleMode === "all"}
            onChange={() => set({ subtitleMode: "all" })}
          >
            Keep all subtitles
          </Radio>
          <Radio
            name="subs"
            checked={choices.subtitleMode === "only"}
            onChange={() => set({ subtitleMode: "only" })}
          >
            Keep only these languages
          </Radio>
          {choices.subtitleMode === "only" && (
            <div className="pl-8">
              <LanguagePicker
                id="batch-subtitle-languages"
                label="Add a subtitle language to keep"
                value={choices.subtitleLanguages}
                onChange={(codes) => set({ subtitleLanguages: codes })}
              />
            </div>
          )}
          <Radio
            name="subs"
            checked={choices.subtitleMode === "none"}
            onChange={() => set({ subtitleMode: "none" })}
          >
            Remove all subtitles
          </Radio>
        </fieldset>
        <div className="flex flex-col gap-1">
          <Tick checked={choices.removeCommentary} onChange={(v) => set({ removeCommentary: v })}>
            Also remove commentary tracks
          </Tick>
          <Tick checked={choices.overwrite} onChange={(v) => set({ overwrite: v })}>
            Replace “- Tailarr” copies made before
          </Tick>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="batch-default-audio" className="font-medium">
          Default audio
        </label>
        <LanguageSelect
          id="batch-default-audio"
          value={choices.defaultAudio}
          onChange={(code) => set({ defaultAudio: code })}
          noneLabel="Don't change the default audio"
        />
        <p className="text-xs text-muted-foreground">
          The first ordinary track in this language becomes the default (not commentary or audio
          description).
        </p>
      </div>
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 font-medium">Default subtitles</legend>
        <Radio
          name="default-subs"
          checked={choices.defaultSubtitles === "keep"}
          onChange={() => set({ defaultSubtitles: "keep" })}
        >
          Don't change
        </Radio>
        <Radio
          name="default-subs"
          checked={choices.defaultSubtitles === "off"}
          onChange={() => set({ defaultSubtitles: "off" })}
        >
          No subtitles unless chosen (forced subtitles still show)
        </Radio>
        <Radio
          name="default-subs"
          checked={choices.defaultSubtitles === "language"}
          onChange={() => set({ defaultSubtitles: "language" })}
        >
          Show subtitles in a language
        </Radio>
        {choices.defaultSubtitles === "language" && (
          <div className="pl-8">
            <LanguageSelect
              id="batch-default-subtitles"
              value={choices.defaultSubtitleLanguage}
              onChange={(code) => set({ defaultSubtitleLanguage: code })}
              noneLabel="Choose a language…"
            />
          </div>
        )}
      </fieldset>
    </div>
  );
}

function PreviewSummary({
  preview,
  allowHardlinked,
  onAllowHardlinked,
}: {
  preview: BatchPreview;
  allowHardlinked: boolean;
  onAllowHardlinked: (value: boolean) => void;
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
        <span className="font-medium">{plural(preview.will_run, "episode")}</span> will{" "}
        {preview.changes_originals ? "be changed" : "get a copy"}
        {skipped.length > 0 && <>, {skipped.length} skipped</>}.
      </p>
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
              Some episodes are also in your downloads (still seeding). Changing them also changes
              the seeding copy, which can break the torrent, so they're skipped unless you tick
              this.
            </p>
          </div>
          <Tick checked={allowHardlinked} onChange={onAllowHardlinked}>
            I understand: change seeding episodes too
          </Tick>
        </div>
      )}
      {running.length > 0 && (
        <div>
          <p className="mb-2 font-medium">
            {preview.changes_originals ? "Will be changed" : "Copies to make"}
          </p>
          <ul className="flex flex-col gap-1.5" aria-label="Episodes that will change">
            {running.map((file) => (
              <li key={file.episode_id} className="rounded-lg border px-3 py-2">
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
              </li>
            ))}
          </ul>
        </div>
      )}
      {skipped.length > 0 && (
        <details className="rounded-lg border px-3 py-2" open={running.length === 0}>
          <summary className="min-h-9 cursor-pointer py-1 font-medium">
            Skipped ({skipped.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-2" aria-label="Skipped episodes">
            {skipped.map((file) => (
              <li key={file.episode_id} className="flex gap-2">
                <MinusCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="[overflow-wrap:anywhere]">
                  <span className="font-medium">{file.label}</span>
                  <span className="text-muted-foreground"> – {file.reason}</span>
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
              {!space.enough && ". Not enough: free up some space or choose one season at a time."}
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

/**
 * Apply one action to every episode of a season or a whole show. Track numbers differ
 * from episode to episode, so choices are made by language ("keep only English
 * subtitles"), and the summary shows what that means for each episode before anything
 * starts. One job per episode, shown as a group in the queue.
 */
export function BatchDialog({
  showId,
  season,
  scopeLabel,
  open,
  onOpenChange,
}: {
  showId: number;
  /** null: the whole show. */
  season: number | null;
  scopeLabel: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("choose");
  const [choices, setChoices] = useState<Choices>(START);
  const [allowHardlinked, setAllowHardlinked] = useState(false);
  const [started, setStarted] = useState<BatchStarted | null>(null);

  const request = (allow = allowHardlinked): BatchRequest => ({
    season,
    action: actionOf(choices),
    allow_hardlinked: allow,
  });
  const preview = useMutation({
    mutationFn: (allow: boolean) => api.previewBatch(showId, request(allow)),
    onSuccess: () => setStep("preview"),
  });
  const start = useMutation({
    mutationFn: () => api.startBatch(showId, request()),
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
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 font-medium">What should Tailarr do?</legend>
          {KINDS.map(({ kind, icon: Icon, title, text }) => (
            <label
              key={kind}
              className={cn(
                "flex cursor-pointer gap-3 rounded-xl border p-3 transition",
                choices.kind === kind ? "border-primary bg-accent/40" : "hover:bg-muted",
              )}
            >
              <input
                type="radio"
                name="batch-kind"
                checked={choices.kind === kind}
                onChange={() => set({ kind })}
                className="mt-1 size-5 shrink-0 cursor-pointer accent-primary"
              />
              <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
              <span>
                <span className="block font-medium">{title}</span>
                <span className="block text-muted-foreground">{text}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <div className="rounded-xl border p-3">
          <Options choices={choices} set={set} />
        </div>
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
          {preview.isPending ? "Checking every episode…" : "Show what will happen"}
        </Button>
      </>
    );
  } else if (step === "preview" && data) {
    body = (
      <PreviewSummary
        preview={data}
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
            ? "Choose what to do to every episode. You'll see exactly what happens to each one before anything starts."
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
