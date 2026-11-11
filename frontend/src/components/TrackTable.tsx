import { Check, Minus, Pencil } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import type { Track, TrackType } from "@/lib/api";
import { explainHdr } from "@/lib/hdr";
import { cn } from "@/lib/utils";

const GROUP_TITLES: Record<TrackType, string> = {
  video: "Video",
  audio: "Audio",
  subtitles: "Subtitles",
};

/** A track's settings as the owner has set them on the page (saved or not). */
export type TrackValues = { default: boolean; forced: boolean; name: string };

/** Switches and name boxes instead of plain text, for changing track settings. */
export type TrackEditing = {
  values: (track: Track) => TrackValues;
  changed: (track: Track) => boolean;
  onChange: (track: Track, change: Partial<TrackValues>) => void;
  disabled?: boolean;
};

/** "Audio 2: French" — how a track is named in labels and summaries. */
export function trackLabel(track: Track, tracks: Track[]): string {
  const same = tracks.filter((t) => t.type === track.type);
  const label = `${GROUP_TITLES[track.type]} ${same.indexOf(track) + 1}`;
  return track.type === "video" && track.language === "und"
    ? label
    : `${label}: ${track.language_name}`;
}

/** "Dolby TrueHD Atmos · 7.1", "PGS (picture-based)". */
export function trackFormat(track: Track): string {
  if (track.type === "audio") {
    return [track.codec, track.channel_layout].filter(Boolean).join(" · ");
  }
  if (track.type === "subtitles") {
    return `${track.codec} (${track.picture_based ? "picture-based" : "text"})`;
  }
  return track.codec;
}

/** "3840 × 2160 · 23.976 fps · 10-bit". */
export function pictureDetails(track: Track): string {
  return [
    track.width && track.height ? `${track.width} × ${track.height}` : null,
    track.frame_rate ? `${track.frame_rate} fps` : null,
    track.bit_depth ? `${track.bit_depth}-bit` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function language(track: Track): string {
  // Video tracks rarely have a meaningful language.
  if (track.type === "video" && track.language === "und") return "—";
  return track.language_name;
}

/** Small labels for the extra flags some tracks carry. */
function TrackFlags({ track }: { track: Track }) {
  const flags = [
    track.hearing_impaired && [
      "SDH",
      "For deaf and hard-of-hearing viewers (describes sounds too)",
    ],
    track.visual_impaired && ["Audio description", "Describes what's on screen, for blind viewers"],
    track.commentary && ["Commentary", "Commentary track"],
    track.original && ["Original language", "The language the film was made in"],
    !track.enabled && ["Switched off", "Players are told to ignore this track"],
  ].filter(Boolean) as [string, string][];
  if (flags.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {flags.map(([label, title]) => (
        <Badge key={label} title={title}>
          {label}
        </Badge>
      ))}
    </span>
  );
}

function YesNo({ value, label }: { value: boolean; label: string }) {
  return value ? (
    <span className="inline-flex items-center gap-1 font-medium text-primary">
      <Check className="size-4" aria-hidden />
      <span className="sr-only">{label}: yes</span>
    </span>
  ) : (
    <span className="text-muted-foreground">
      <Minus className="size-4" aria-hidden />
      <span className="sr-only">{label}: no</span>
    </span>
  );
}

function hdrText(track: Track): string {
  return explainHdr(track.hdr).title;
}

/** The track's title, or a box to rename it. */
function TrackName({
  track,
  label,
  editing,
}: {
  track: Track;
  label: string;
  editing?: TrackEditing;
}) {
  const [renaming, setRenaming] = useState(false);
  if (!editing) {
    return <span>{track.name || <span className="text-muted-foreground">—</span>}</span>;
  }
  const name = editing.values(track).name;
  if (renaming) {
    return (
      <input
        aria-label={`Name of ${label}`}
        value={name}
        maxLength={200}
        autoFocus
        disabled={editing.disabled}
        placeholder="No name"
        onChange={(e) => editing.onChange(track, { name: e.target.value })}
        onBlur={() => setRenaming(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "Escape") setRenaming(false);
        }}
        className="h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-ring md:h-9 md:text-sm"
      />
    );
  }
  return (
    <span className="flex items-center gap-1">
      <span className={cn("min-w-0", name !== track.name && "font-medium text-primary")}>
        {name || <span className="text-muted-foreground">No name</span>}
      </span>
      <button
        type="button"
        onClick={() => setRenaming(true)}
        disabled={editing.disabled}
        aria-label={`Rename ${label}`}
        title="Rename"
        className="-my-2 inline-flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50 md:size-8"
      >
        <Pencil className="size-3.5" aria-hidden />
      </button>
    </span>
  );
}

/** A Default or Forced setting: a switch when editing, otherwise a tick or a dash. */
function FlagCell({
  track,
  flag,
  label,
  editing,
}: {
  track: Track;
  flag: "default" | "forced";
  label: string;
  editing?: TrackEditing;
}) {
  const word = flag === "default" ? "Default" : "Forced";
  // Forced only means something for subtitles; audio keeps showing what the file says.
  if (!editing || (flag === "forced" && track.type !== "subtitles")) {
    return <YesNo value={track[flag]} label={word} />;
  }
  return (
    <Switch
      checked={editing.values(track)[flag]}
      onCheckedChange={(checked) => editing.onChange(track, { [flag]: checked })}
      disabled={editing.disabled}
      aria-label={`${word}: ${label}`}
    />
  );
}

const HEAD =
  "px-3 py-2 text-left text-xs font-medium tracking-wide text-muted-foreground uppercase";
const CELL = "px-3 py-2.5 align-top";

/** Desktop: one table per track group. */
function GroupTable({
  type,
  tracks,
  all,
  editing,
}: {
  type: TrackType;
  tracks: Track[];
  all: Track[];
  editing?: TrackEditing;
}) {
  const video = type === "video";
  return (
    <table className="w-full text-sm">
      <thead className="border-b">
        <tr>
          {video ? (
            <>
              <th className={HEAD}>Format</th>
              <th className={HEAD}>Picture</th>
              <th className={HEAD}>HDR</th>
              <th className={HEAD}>Title</th>
            </>
          ) : (
            <>
              <th className={HEAD}>Language</th>
              <th className={HEAD}>Format</th>
              <th className={HEAD}>Title</th>
              <th className={cn(HEAD, "w-20 text-center")}>Default</th>
              <th className={cn(HEAD, "w-20 text-center")}>Forced</th>
            </>
          )}
        </tr>
      </thead>
      <tbody className="divide-y">
        {tracks.map((track) => (
          <tr
            key={track.id}
            data-testid={`track-${track.id}`}
            className={cn(
              editing && "[&>td]:align-middle",
              editing?.changed(track) && "bg-accent/40",
            )}
          >
            {video ? (
              <>
                <td className={CELL}>{trackFormat(track)}</td>
                <td className={CELL}>
                  {track.resolution && <span className="font-medium">{track.resolution} </span>}
                  <span className="text-muted-foreground">{pictureDetails(track)}</span>
                </td>
                <td className={CELL}>{hdrText(track)}</td>
                <td className={cn(CELL, "[overflow-wrap:anywhere]")}>
                  <TrackName track={track} label={trackLabel(track, all)} editing={editing} />
                </td>
              </>
            ) : (
              <>
                <td className={cn(CELL, "font-medium")}>{language(track)}</td>
                <td className={CELL}>{trackFormat(track)}</td>
                <td className={cn(CELL, "[overflow-wrap:anywhere]")}>
                  <div className="flex flex-col gap-1">
                    <TrackName track={track} label={trackLabel(track, all)} editing={editing} />
                    <TrackFlags track={track} />
                  </div>
                </td>
                <td className={cn(CELL, "text-center", editing && "py-1")}>
                  <FlagCell
                    track={track}
                    flag="default"
                    label={trackLabel(track, all)}
                    editing={editing}
                  />
                </td>
                <td className={cn(CELL, "text-center", editing && "py-1")}>
                  <FlagCell
                    track={track}
                    flag="forced"
                    label={trackLabel(track, all)}
                    editing={editing}
                  />
                </td>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Phones: one compact card per track. */
function GroupCards({
  tracks,
  all,
  editing,
}: {
  tracks: Track[];
  all: Track[];
  editing?: TrackEditing;
}) {
  return (
    <ul className="flex flex-col gap-2 md:hidden">
      {tracks.map((track) => {
        const label = trackLabel(track, all);
        const values = editing?.values(track);
        return (
          <li
            key={track.id}
            data-testid={`track-card-${track.id}`}
            className={cn(
              "rounded-lg border bg-background/40 px-3 py-2.5 text-sm",
              editing?.changed(track) && "border-primary/60 bg-accent/40",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium">
                {track.type === "video" ? trackFormat(track) : language(track)}
              </p>
              {track.type !== "video" && !editing && (
                <span className="flex shrink-0 gap-1">
                  {track.default && <Badge tone="accent">Default</Badge>}
                  {track.forced && <Badge tone="accent">Forced</Badge>}
                </span>
              )}
            </div>
            <p className="text-muted-foreground">
              {track.type === "video"
                ? [track.resolution, pictureDetails(track), hdrText(track)]
                    .filter(Boolean)
                    .join(" · ")
                : trackFormat(track)}
            </p>
            {editing ? (
              <div className="[overflow-wrap:anywhere]">
                <TrackName track={track} label={label} editing={editing} />
              </div>
            ) : (
              track.name && <p className="[overflow-wrap:anywhere]">“{track.name}”</p>
            )}
            <TrackFlags track={track} />
            {editing && values && track.type !== "video" && (
              <div className="mt-1 flex flex-wrap gap-x-5 border-t pt-1">
                <label className="flex items-center gap-1">
                  <FlagCell track={track} flag="default" label={label} editing={editing} />
                  Default
                </label>
                {track.type === "subtitles" ? (
                  <label className="flex items-center gap-1">
                    <FlagCell track={track} flag="forced" label={label} editing={editing} />
                    Forced
                  </label>
                ) : (
                  track.forced && (
                    <span className="flex items-center">
                      <Badge tone="accent">Forced</Badge>
                    </span>
                  )
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const GROUP_HELP: Partial<Record<TrackType, string>> = {
  audio: "Default: the audio players choose first.",
  subtitles:
    "Default: shown automatically. Forced: subtitles only for foreign-language parts, " +
    "shown even when subtitles are off.",
};

/** The tracks of one file, grouped Video / Audio / Subtitles. */
export function TrackTable({ tracks, editing }: { tracks: Track[]; editing?: TrackEditing }) {
  return (
    <div className="flex flex-col gap-6">
      {(["video", "audio", "subtitles"] as const).map((type) => {
        const group = tracks.filter((t) => t.type === type);
        const headingId = `tracks-${type}`;
        return (
          <section key={type} aria-labelledby={headingId}>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
              <h3 id={headingId} className="text-sm font-semibold">
                {GROUP_TITLES[type]}{" "}
                <span className="font-normal text-muted-foreground">({group.length})</span>
              </h3>
              {group.length > 0 && GROUP_HELP[type] && (
                <p className="text-xs text-muted-foreground">{GROUP_HELP[type]}</p>
              )}
            </div>
            {group.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No {GROUP_TITLES[type].toLowerCase()} tracks.
              </p>
            ) : (
              <>
                <div className="hidden overflow-x-auto rounded-lg border md:block">
                  <GroupTable type={type} tracks={group} all={tracks} editing={editing} />
                </div>
                <GroupCards tracks={group} all={tracks} editing={editing} />
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
