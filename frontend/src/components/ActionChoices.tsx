import { Copy, SlidersHorizontal, Sparkles, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { LanguagePicker, LanguageSelect } from "@/components/LanguagePicker";
import { Checkbox } from "@/components/ui/checkbox";
import type { BatchAction } from "@/lib/api";
import { cn } from "@/lib/utils";

/*
 * Choosing an action by language rather than by track number: shared by "Change this
 * season…" (TV) and the rule editor.
 */

export type Kind = BatchAction["type"];

export const KINDS: { kind: Kind; icon: LucideIcon; title: string; text: string }[] = [
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

export type Choices = {
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
  /** HDR10 copies: also change tracks in the same copy. */
  hdr10Tracks: boolean;
};

export const START: Choices = {
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
  hdr10Tracks: false,
};

export function actionOf(c: Choices): BatchAction {
  if (c.kind === "hdr10_copy") {
    if (!c.hdr10Tracks) return { type: "hdr10_copy", overwrite: c.overwrite };
    return {
      type: "hdr10_copy",
      overwrite: c.overwrite,
      audio: { mode: c.audioMode, languages: c.audioMode === "only" ? c.audioLanguages : [] },
      subtitles: {
        mode: c.subtitleMode,
        languages: c.subtitleMode === "only" ? c.subtitleLanguages : [],
      },
      remove_commentary: c.removeCommentary,
      default_audio: c.defaultAudio,
      default_subtitles: c.defaultSubtitles,
      default_subtitle_language:
        c.defaultSubtitles === "language" ? c.defaultSubtitleLanguage : null,
    };
  }
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
  if (c.kind === "hdr10_copy" && c.hdr10Tracks) {
    if (c.audioMode === "only" && c.audioLanguages.length === 0)
      return "Choose at least one audio language to keep.";
    if (c.subtitleMode === "only" && c.subtitleLanguages.length === 0)
      return "Choose at least one subtitle language to keep.";
    if (c.defaultSubtitles === "language" && !c.defaultSubtitleLanguage)
      return "Choose the subtitle language to show by default.";
  }
  if (c.kind === "default_tracks") {
    if (!c.defaultAudio && c.defaultSubtitles === "keep")
      return "Choose a default audio language or default subtitles.";
    if (c.defaultSubtitles === "language" && !c.defaultSubtitleLanguage)
      return "Choose the subtitle language to show by default.";
  }
  return null;
}

export function Radio({
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

export function Tick({
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

export function ActionOptions({
  choices,
  set,
}: {
  choices: Choices;
  set: (c: Partial<Choices>) => void;
}) {
  if (choices.kind === "hdr10_copy") {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground">
          Files without Dolby Vision are skipped, and so are Dolby Vision profile 5 files (they have
          no HDR10 picture underneath, so the colours would be wrong).
        </p>
        <Tick checked={choices.overwrite} onChange={(v) => set({ overwrite: v })}>
          Replace HDR10 copies Tailarr made before
        </Tick>
        <Tick checked={choices.hdr10Tracks} onChange={(v) => set({ hdr10Tracks: v })}>
          Also change tracks in the copies (in the same go, no extra time)
        </Tick>
        {choices.hdr10Tracks && (
          <div className="mt-2 flex flex-col gap-4 border-l-2 border-primary/40 pl-4">
            <KeepOptions choices={choices} set={set} />
            <DefaultOptions choices={choices} set={set} />
          </div>
        )}
      </div>
    );
  }
  if (choices.kind === "remove_tracks") {
    return (
      <div className="flex flex-col gap-4">
        <KeepOptions choices={choices} set={set} />
        <div className="flex flex-col gap-1">
          <Tick checked={choices.overwrite} onChange={(v) => set({ overwrite: v })}>
            Replace “- Tailarr” copies made before
          </Tick>
        </div>
      </div>
    );
  }
  return <DefaultOptions choices={choices} set={set} />;
}

/** Which audio and subtitle tracks to keep, by language. */
function KeepOptions({ choices, set }: { choices: Choices; set: (c: Partial<Choices>) => void }) {
  return (
    <>
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
              Tracks with no language set are left out too. A file that would be left with no sound
              is skipped and flagged.
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
            <p className="mt-1 text-xs text-muted-foreground">
              Files that would be left with no subtitles at all are flagged in the summary.
            </p>
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
      <Tick checked={choices.removeCommentary} onChange={(v) => set({ removeCommentary: v })}>
        Also remove commentary tracks
      </Tick>
    </>
  );
}

/** Which audio and subtitles players pick by themselves. */
function DefaultOptions({
  choices,
  set,
}: {
  choices: Choices;
  set: (c: Partial<Choices>) => void;
}) {
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

/** The choices that give back an action (for editing a saved rule). */
export function choicesFromAction(action: BatchAction): Choices {
  if (action.type === "hdr10_copy") {
    const tracks = Boolean(
      (action.audio && action.audio.mode !== "all") ||
      (action.subtitles && action.subtitles.mode !== "all") ||
      action.remove_commentary ||
      action.default_audio ||
      (action.default_subtitles && action.default_subtitles !== "keep"),
    );
    return {
      ...START,
      kind: "hdr10_copy",
      overwrite: !!action.overwrite,
      hdr10Tracks: tracks,
      audioMode: action.audio?.mode === "only" ? "only" : tracks ? "all" : START.audioMode,
      audioLanguages: action.audio?.mode === "only" ? action.audio.languages : START.audioLanguages,
      subtitleMode: tracks ? (action.subtitles?.mode ?? "all") : START.subtitleMode,
      subtitleLanguages:
        action.subtitles?.mode === "only" ? action.subtitles.languages : START.subtitleLanguages,
      removeCommentary: !!action.remove_commentary,
      defaultAudio: action.default_audio ?? null,
      defaultSubtitles: action.default_subtitles ?? "keep",
      defaultSubtitleLanguage: action.default_subtitle_language ?? null,
    };
  }
  if (action.type === "remove_tracks") {
    return {
      ...START,
      kind: "remove_tracks",
      overwrite: !!action.overwrite,
      audioMode: action.audio.mode === "only" ? "only" : "all",
      audioLanguages: action.audio.mode === "only" ? action.audio.languages : START.audioLanguages,
      subtitleMode: action.subtitles.mode,
      subtitleLanguages:
        action.subtitles.mode === "only" ? action.subtitles.languages : START.subtitleLanguages,
      removeCommentary: action.remove_commentary,
    };
  }
  return {
    ...START,
    kind: "default_tracks",
    defaultAudio: action.audio_language,
    defaultSubtitles: action.subtitles,
    defaultSubtitleLanguage: action.subtitle_language,
  };
}

/** The three big "what should Tailarr do?" cards. */
export function ActionKindPicker({
  value,
  onChange,
  name,
  noun = { one: "episode", many: "episodes" },
}: {
  value: Kind;
  onChange: (kind: Kind) => void;
  name: string;
  /** What the action is applied to: episodes, films or (rules) files. */
  noun?: { one: string; many: string };
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 font-medium">What should Tailarr do?</legend>
      {KINDS.map(({ kind, icon: Icon, title, text }) => (
        <label
          key={kind}
          className={cn(
            "flex cursor-pointer gap-3 rounded-xl border p-3 transition",
            value === kind ? "border-primary bg-accent/40" : "hover:bg-muted",
          )}
        >
          <input
            type="radio"
            name={name}
            checked={value === kind}
            onChange={() => onChange(kind)}
            className="mt-1 size-5 shrink-0 cursor-pointer accent-primary"
          />
          <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
          <span>
            <span className="block font-medium">{title}</span>
            <span className="block text-muted-foreground">
              {text
                .replace(/episodes/g, noun.many)
                .replace(/episode/g, noun.one)
                .replace(/Episodes/g, noun.many[0].toUpperCase() + noun.many.slice(1))}
            </span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
