import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clapperboard, FileVideo, Link2, ListVideo } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { Poster } from "@/components/Poster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type FilmDetail, type FilmFile } from "@/lib/api";
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

function FileRow({ file }: { file: FilmFile }) {
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <FileVideo className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium break-words">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatSize(file.size)} · Changed {formatDate(file.modified_at)}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 pl-8">
        {file.is_main && <Badge tone="accent">Main file</Badge>}
        {file.is_copy && <Badge>Copy made by Tailarr</Badge>}
        {!file.is_mkv && <Badge tone="warning">Not an MKV file</Badge>}
        {file.hardlinked && (
          <Badge tone="warning">
            <Link2 className="size-3" aria-hidden />
            Also in your downloads
          </Badge>
        )}
      </div>
      {file.hardlinked && (
        <p className="pl-8 text-xs text-muted-foreground">
          This file is hardlinked: the same file is also in another folder, usually because it's
          still seeding in your download client. Making a new copy is always safe. Changing this
          file directly would also change the seeding copy.
        </p>
      )}
      {!file.is_mkv && (
        <p className="pl-8 text-xs text-muted-foreground">
          Tailarr can only change MKV files, so this one is shown for information only.
        </p>
      )}
    </li>
  );
}

function Header({ film }: { film: FilmDetail }) {
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

  const data = film.data;
  return (
    <>
      <BackLink />
      <Header film={data} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Files</CardTitle>
            <CardDescription>The video files in this film's folder.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {data.files.map((file) => (
                <FileRow key={file.name} file={file} />
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card className="self-start">
          <CardHeader>
            <div className="mb-1 flex size-10 items-center justify-center rounded-full bg-accent text-accent-foreground">
              <ListVideo className="size-5" aria-hidden />
            </div>
            <CardTitle>Tracks and HDR coming next</CardTitle>
            <CardDescription>
              The next update shows each file's video, audio and subtitle tracks, and whether it has
              Dolby Vision, HDR10 or HDR10+.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </>
  );
}
