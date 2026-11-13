import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Layers, Tv, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { BatchDialog } from "@/components/BatchDialog";
import { EmptyState } from "@/components/EmptyState";
import { MediaBadges } from "@/components/MediaBadges";
import { ShowHeader } from "@/components/ShowHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Episode, type Season, type ShowDetail } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";

function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Button asChild variant="ghost" className="-ml-3 mb-3">
      <Link to={to}>
        <ArrowLeft aria-hidden />
        {label}
      </Link>
    </Button>
  );
}

function EpisodeRow({ episode }: { episode: Episode }) {
  return (
    <li>
      <Link
        to={`/tv/episodes/${episode.id}`}
        className="flex min-h-14 items-center gap-3 px-3 py-2 hover:bg-muted md:px-4"
      >
        <span className="w-20 shrink-0 text-sm font-medium text-muted-foreground tabular-nums">
          {episode.label || "—"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            {episode.title || episode.main_file}
          </span>
          <span className="mt-1 flex flex-wrap gap-1">
            <MediaBadges media={episode.media} />
            {episode.has_copy && <Badge>Has a Tailarr copy</Badge>}
            {!episode.is_mkv && <Badge tone="warning">Not MKV</Badge>}
          </span>
        </span>
        <span className="hidden w-20 shrink-0 text-right text-sm text-muted-foreground tabular-nums sm:block">
          {formatSize(episode.size)}
        </span>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </Link>
    </li>
  );
}

type Batch = { season: number | null; label: string };

function SeasonCard({ season, onBatch }: { season: Season; onBatch: (batch: Batch) => void }) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div>
          <CardTitle>{season.label}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {plural(season.episodes.length, "episode")} · {formatSize(season.size)}
          </p>
        </div>
        {season.season !== null && (
          <Button
            variant="secondary"
            onClick={() => onBatch({ season: season.season, label: season.label.toLowerCase() })}
          >
            <Layers aria-hidden />
            Change this season…
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0 md:p-0">
        <ul className="divide-y border-t" aria-label={`${season.label} episodes`}>
          {season.episodes.map((episode) => (
            <EpisodeRow key={episode.id} episode={episode} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ShowDetailView({ show }: { show: ShowDetail }) {
  const [batch, setBatch] = useState<Batch | null>(null);
  return (
    <>
      <BackLink to="/tv" label="TV" />
      <ShowHeader title={show.title} posterUrl={show.poster_url} backdropUrl={show.backdrop_url}>
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
          {show.title}
          {show.year && (
            <span className="ml-2 font-normal text-muted-foreground">({show.year})</span>
          )}
        </h1>
        <p className="text-sm text-muted-foreground">
          {show.season_count > 0 && `${plural(show.season_count, "season")} · `}
          {plural(show.episode_count, "episode")} · {formatSize(show.size)}
        </p>
        <MediaBadges media={show.media} />
        {show.dv_episodes > 0 && (
          <p className="text-sm text-muted-foreground">
            {plural(show.dv_episodes, "episode")} with Dolby Vision
          </p>
        )}
        <p className="text-xs break-all text-muted-foreground">{show.folder}</p>
        <div className="mt-1">
          <Button onClick={() => setBatch({ season: null, label: "every episode" })}>
            <Wand2 aria-hidden />
            Change the whole show…
          </Button>
        </div>
      </ShowHeader>
      <p className="mb-4 text-sm text-muted-foreground">
        Open an episode to see its tracks and change it on its own, or use{" "}
        <span className="font-medium text-foreground">Change this season</span> to do the same to
        many episodes at once. You'll always see a summary first.
      </p>
      <div className="flex flex-col gap-6">
        {show.seasons.map((season) => (
          <SeasonCard key={season.label} season={season} onBatch={setBatch} />
        ))}
      </div>
      {batch && (
        <BatchDialog
          target={{ kind: "show", showId: show.id, season: batch.season }}
          scopeLabel={`${batch.label} of ${show.title}`}
          hasCopies={show.seasons
            .filter((s) => batch.season === null || s.season === batch.season)
            .some((s) => s.episodes.some((e) => e.has_copy))}
          open
          onOpenChange={(open) => !open && setBatch(null)}
        />
      )}
    </>
  );
}

export function ShowPage() {
  const { id = "" } = useParams();
  const show = useQuery({
    queryKey: ["tv", "show", id],
    queryFn: () => api.show(id),
    retry: false,
  });
  if (show.isPending) {
    return (
      <>
        <BackLink to="/tv" label="TV" />
        <Skeleton className="mb-6 h-48 w-full md:h-64" />
        <Skeleton className="h-40 w-full" />
      </>
    );
  }
  if (show.isError) {
    return (
      <>
        <BackLink to="/tv" label="TV" />
        <EmptyState icon={Tv} title="Show not found">
          <p>{show.error.message}</p>
        </EmptyState>
      </>
    );
  }
  return <ShowDetailView show={show.data} />;
}
