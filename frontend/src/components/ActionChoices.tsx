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

/** The choices that give back an action (for editing a saved rule). */
export function choicesFromAction(action: BatchAction): Choices {
  if (action.type === "hdr10_copy")
    return { ...START, kind: "hdr10_copy", overwrite: !!action.overwrite };
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
  wording = "episodes",
}: {
  value: Kind;
  onChange: (kind: Kind) => void;
  name: string;
  wording?: "episodes" | "files";
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
              {wording === "files"
                ? text.replace(/episodes?/g, (w) => (w === "episode" ? "file" : "files"))
                : text}
            </span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
