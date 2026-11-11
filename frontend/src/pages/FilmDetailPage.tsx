import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clapperboard, FileVideo, Link2 } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { FileContents } from "@/components/FileContents";
import { MediaBadges } from "@/components/MediaBadges";
import { Poster } from "@/components/Poster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type FilmDetail as FilmDetailData, type FilmFile } from "@/lib/api";
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
          <p className="text-sm font-medium [overflow-wrap:anywhere]">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatSize(file.size)} · Changed {formatDate(file.modified_at)}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 pl-8">
        {file.is_main && <Badge tone="accent">Main file</Badge>}
        <MediaBadges media={file.media} />
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

function fileLabel(file: FilmFile): string {
  if (file.is_main) return `Main file: ${file.name}`;
  if (file.is_copy) return `Copy: ${file.name}`;
  return file.name;
}

function FilmDetail({ film }: { film: FilmDetailData }) {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("file");
  const selected =
    film.files.find((f) => f.name === wanted) ?? film.files.find((f) => f.is_main) ?? film.files[0];

  function choose(name: string) {
    const next = new URLSearchParams(params);
    if (name === film.main_file) next.delete("file");
    else next.set("file", name);
    setParams(next, { replace: true });
  }

  return (
    <>
      <BackLink />
      <Header film={film} />
      <div className="flex flex-col gap-6">
        {selected && (
          <Card>
            <CardHeader>
              <CardTitle>What's inside</CardTitle>
              <CardDescription>
                The picture, sound and subtitle tracks, read with MKVToolNix and MediaInfo.
              </CardDescription>
              {film.files.length > 1 && (
                <div className="mt-2 flex flex-col gap-1.5">
                  <label htmlFor="file-choice" className="text-sm font-medium">
                    File
                  </label>
                  <select
                    id="file-choice"
                    value={selected.name}
                    onChange={(e) => choose(e.target.value)}
                    className="h-11 w-full max-w-full min-w-0 cursor-pointer truncate rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm"
                  >
                    {film.files.map((file) => (
                      <option key={file.name} value={file.name}>
                        {fileLabel(file)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </CardHeader>
            <CardContent>
              <FileContents
                key={selected.name}
                queryKey={["films", String(film.id), "media", selected.name]}
                load={(refresh) => api.filmMedia(film.id, selected.name, refresh)}
              />
            </CardContent>
          </Card>
        )}
        <Card>
          <CardHeader>
            <CardTitle>Files</CardTitle>
            <CardDescription>The video files in this film's folder.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {film.files.map((file) => (
                <FileRow key={file.name} file={file} />
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
