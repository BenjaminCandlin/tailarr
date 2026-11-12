import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clapperboard } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ItemFiles } from "@/components/ItemFiles";
import { MediaBadges } from "@/components/MediaBadges";
import { Poster } from "@/components/Poster";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type FilmDetail as FilmDetailData } from "@/lib/api";
import { formatDate, formatSize, plural } from "@/lib/format";

function BackLink() {
  return (
    <Button asChild variant="ghost" className="-ml-3 mb-3">
      <Link to="/films">
        <ArrowLeft aria-hidden />
        Films
      </Link>
    </Button>
  );
}

function Header({ film }: { film: FilmDetailData }) {
  return (
    <div className="relative mb-6 overflow-hidden rounded-xl border bg-card">
      {film.backdrop_url && (
        <img
          src={film.backdrop_url}
          alt=""
          className="absolute inset-0 size-full object-cover opacity-25"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-card via-card/90 to-card/40" />
      <div className="relative flex gap-4 p-4 md:gap-6 md:p-6">
        <Poster
          src={film.poster_url && film.poster_url.replace("?", "?size=full&")}
          title={film.title}
          className="w-28 shrink-0 shadow-lg md:w-44"
        />
        <div className="flex min-w-0 flex-col gap-2 py-1">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            {film.title}
            {film.year && (
              <span className="ml-2 font-normal text-muted-foreground">({film.year})</span>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            {plural(film.file_count, "file")} · {formatSize(film.size)} · Added{" "}
            {formatDate(film.added_at)}
          </p>
          <MediaBadges media={film.media} />
          <p className="text-xs break-all text-muted-foreground">{film.folder}</p>
        </div>
      </div>
    </div>
  );
}

export function FilmDetailPage() {
  const { id = "" } = useParams();
  const film = useQuery({ queryKey: ["films", id], queryFn: () => api.film(id), retry: false });

  if (film.isPending) {
    return (
      <>
        <BackLink />
        <Skeleton className="mb-6 h-48 w-full md:h-72" />
        <Skeleton className="h-40 w-full" />
      </>
    );
  }
  if (film.isError) {
    return (
      <>
        <BackLink />
        <EmptyState icon={Clapperboard} title="Film not found">
          <p>{film.error.message}</p>
        </EmptyState>
      </>
    );
  }

  return <FilmDetail film={film.data} />;
}

function FilmDetail({ film }: { film: FilmDetailData }) {
  return (
    <>
      <BackLink />
      <Header film={film} />
      <ItemFiles
        item={{ kind: "films", id: film.id }}
        files={film.files}
        mainFile={film.main_file}
        folderWord="film"
      />
    </>
  );
}
