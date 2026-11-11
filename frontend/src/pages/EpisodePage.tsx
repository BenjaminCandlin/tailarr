import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Tv } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ItemFiles } from "@/components/ItemFiles";
import { MediaBadges } from "@/components/MediaBadges";
import { ShowHeader } from "@/components/ShowHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type EpisodeDetail } from "@/lib/api";
import { formatDate, formatSize, plural } from "@/lib/format";

function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Button asChild variant="ghost" className="-ml-3 mb-3 max-w-full">
      <Link to={to}>
        <ArrowLeft aria-hidden />
        <span className="truncate">{label}</span>
      </Link>
    </Button>
  );
}

function EpisodeView({ episode }: { episode: EpisodeDetail }) {
  return (
    <>
      <BackLink to={`/tv/shows/${episode.show_id}`} label={episode.show_title} />
      <ShowHeader
        title={episode.show_title}
        posterUrl={episode.poster_url}
        backdropUrl={episode.backdrop_url}
      >
        <p className="text-sm font-medium text-muted-foreground">
          {episode.show_title}
          {episode.label && ` · ${episode.label}`}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] md:text-3xl">
          {episode.title || episode.main_file}
        </h1>
        <p className="text-sm text-muted-foreground">
          {plural(episode.file_count, "file")} · {formatSize(episode.size)} · Added{" "}
          {formatDate(episode.added_at)}
        </p>
        <MediaBadges media={episode.media} />
        <p className="text-xs break-all text-muted-foreground">{episode.folder}</p>
      </ShowHeader>
      <ItemFiles
        item={{ kind: "episodes", id: episode.id }}
        files={episode.files}
        mainFile={episode.main_file}
        folderWord="episode"
      />
    </>
  );
}

export function EpisodePage() {
  const { id = "" } = useParams();
  const episode = useQuery({
    queryKey: ["episodes", id],
    queryFn: () => api.episode(id),
    retry: false,
  });
  if (episode.isPending) {
    return (
      <>
        <BackLink to="/tv" label="TV" />
        <Skeleton className="mb-6 h-48 w-full md:h-64" />
        <Skeleton className="h-40 w-full" />
      </>
    );
  }
  if (episode.isError) {
    return (
      <>
        <BackLink to="/tv" label="TV" />
        <EmptyState icon={Tv} title="Episode not found">
          <p>{episode.error.message}</p>
        </EmptyState>
      </>
    );
  }
  return <EpisodeView episode={episode.data} />;
}
