import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileWarning, Info, RefreshCw } from "lucide-react";

import { TrackSettingsEditor } from "@/components/TrackSettingsEditor";
import { TrackTable } from "@/components/TrackTable";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Media } from "@/lib/api";
import { formatDuration, plural } from "@/lib/format";
import { explainHdr } from "@/lib/hdr";
import { cn } from "@/lib/utils";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

function attachmentText(media: Media): string {
  const fonts = media.attachments.filter(
    (a) => a.mime_type.includes("font") || /\.(ttf|otf)$/i.test(a.name),
  ).length;
  const pictures = media.attachments.filter((a) => a.mime_type.startsWith("image/")).length;
  const parts = [];
  if (fonts) parts.push(plural(fonts, "font"));
  if (pictures) parts.push(plural(pictures, "picture"));
  const other = media.attachments.length - fonts - pictures;
  if (other) parts.push(plural(other, "other file"));
  return parts.join(", ") || "None";
}

function HdrNote({ media }: { media: Media }) {
  const info = explainHdr(media.hdr);
  return (
    <div
      className={cn(
        "flex gap-3 rounded-lg border px-4 py-3 text-sm",
        info.warning ? "border-warning/40 bg-warning-soft" : "bg-muted/50",
      )}
      data-testid="hdr-note"
    >
      {info.warning ? (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      ) : (
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      )}
      <div>
        <p className="font-medium">{info.title}</p>
        <p className="text-muted-foreground">{info.text}</p>
        {!media.hdr_checked && (
          <p className="mt-1 text-muted-foreground">
            MediaInfo couldn't read this file, so HDR wasn't checked.
          </p>
        )}
      </div>
    </div>
  );
}

function ReadError({
  media,
  onRetry,
  retrying,
}: {
  media: Media;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning-soft p-4 text-sm"
    >
      <div className="flex gap-3">
        <FileWarning className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden />
        <div>
          <p className="font-medium">Tailarr couldn't look inside this file</p>
          <p>{media.error}</p>
        </div>
      </div>
      {media.error_details && (
        <details className="pl-8">
          <summary className="cursor-pointer text-muted-foreground">Show technical details</summary>
          <pre className="mt-2 max-h-60 overflow-auto rounded bg-background p-3 text-xs whitespace-pre-wrap">
            {media.error_details}
          </pre>
        </details>
      )}
      <div className="pl-8">
        <Button variant="secondary" onClick={onRetry} disabled={retrying}>
          <RefreshCw className={cn(retrying && "animate-spin")} aria-hidden />
          Try again
        </Button>
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <p className="text-sm text-muted-foreground" role="status">
        Reading the file… This can take a few seconds if the disk has to spin up.
      </p>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

/** Everything inside one video file: summary facts, HDR, and the track tables. */
export function FileContents({
  queryKey,
  load,
  edit,
}: {
  queryKey: unknown[];
  load: (refresh: boolean) => Promise<Media>;
  /** Allow changing track settings (MKV files only). */
  edit?: { filmId: number; file: string; onOpenFile?: (name: string) => void };
}) {
  const queryClient = useQueryClient();
  const media = useQuery({ queryKey, queryFn: () => load(false), retry: false });

  // "Try again" reads the file afresh, even if Tailarr remembers it as unreadable.
  const reread = useMutation({
    mutationFn: () => load(true),
    onSuccess: (fresh) => queryClient.setQueryData(queryKey, fresh),
  });

  if (media.isPending) return <Loading />;
  if (media.isError) {
    return (
      <div
        role="alert"
        className="flex gap-3 rounded-lg border border-warning/40 bg-warning-soft p-4 text-sm"
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
        <p>{media.error.message}</p>
      </div>
    );
  }
  const data = media.data;
  if (data.error)
    return <ReadError media={data} onRetry={() => reread.mutate()} retrying={reread.isPending} />;

  const video = data.tracks.find((t) => t.type === "video");
  const audio = data.tracks.filter((t) => t.type === "audio").length;
  const subs = data.tracks.filter((t) => t.type === "subtitles").length;
  return (
    <div className="flex flex-col gap-5">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
        <Fact label="Length">{data.duration ? formatDuration(data.duration) : "Unknown"}</Fact>
        <Fact label="Picture">
          {[data.resolution, video?.frame_rate && `${video.frame_rate} fps`]
            .filter(Boolean)
            .join(" · ") || "Unknown"}
        </Fact>
        <Fact label="HDR">{explainHdr(data.hdr).title}</Fact>
        <Fact label="Tracks">
          {audio} audio, {plural(subs, "subtitle")}
        </Fact>
        <Fact label="Chapters">{data.chapters ? data.chapters : "None"}</Fact>
        <Fact label="Attachments">{attachmentText(data)}</Fact>
      </dl>
      {data.title && (
        <p className="text-sm text-muted-foreground">
          Title stored inside the file: <span className="text-foreground">{data.title}</span>
        </p>
      )}
      <HdrNote media={data} />
      {edit ? (
        <TrackSettingsEditor
          filmId={edit.filmId}
          file={edit.file}
          tracks={data.tracks}
          onOpenFile={edit.onOpenFile}
        />
      ) : (
        <TrackTable tracks={data.tracks} />
      )}
    </div>
  );
}
