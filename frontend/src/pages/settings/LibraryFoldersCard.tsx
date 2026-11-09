import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type LibrarySettings } from "@/lib/api";

function FolderForm({ initial }: { initial: LibrarySettings }) {
  const queryClient = useQueryClient();
  const [movies, setMovies] = useState(initial.movies_dir);
  const [tv, setTv] = useState(initial.tv_dir);
  const save = useMutation({
    mutationFn: api.saveLibrarySettings,
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings", "library"], saved);
      void queryClient.invalidateQueries({ queryKey: ["health"] });
    },
  });
  const changed = movies !== initial.movies_dir || tv !== initial.tv_dir;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ ...initial, movies_dir: movies, tv_dir: tv });
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="movies-dir" className="text-sm font-medium">
          Films folder
        </label>
        <Input
          id="movies-dir"
          value={movies}
          onChange={(e) => setMovies(e.target.value)}
          spellCheck={false}
          autoCapitalize="off"
          aria-invalid={save.isError || undefined}
        />
        <p className="text-xs text-muted-foreground">
          The same folder Radarr uses as its root folder, for example /data/media/movies.
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="tv-dir" className="text-sm font-medium">
          TV folder
        </label>
        <Input
          id="tv-dir"
          value={tv}
          onChange={(e) => setTv(e.target.value)}
          spellCheck={false}
          autoCapitalize="off"
          aria-invalid={save.isError || undefined}
        />
        <p className="text-xs text-muted-foreground">
          The same folder Sonarr uses as its root folder, for example /data/media/tv.
        </p>
      </div>
      {save.isError && (
        <p
          role="alert"
          className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
        >
          {save.error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!changed || save.isPending}>
          {save.isPending ? "Saving…" : "Save folders"}
        </Button>
        {save.isSuccess && !changed ? (
          <p role="status" className="text-sm text-success">
            Saved.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Tailarr only ever looks at files inside these two folders.
          </p>
        )}
      </div>
      <div className="rounded-lg bg-muted px-3 py-2.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Path mapping: </span>
        {initial.path_mappings.length === 0
          ? "none. It isn't needed when Tailarr's /data folder is set up the same way as Radarr's and Sonarr's. You'll be able to add one when connecting Radarr and Sonarr."
          : initial.path_mappings.map((m) => `${m.remote} → ${m.local}`).join(", ")}
      </div>
    </form>
  );
}

export function LibraryFoldersCard() {
  const settings = useQuery({ queryKey: ["settings", "library"], queryFn: api.librarySettings });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Library folders</CardTitle>
        <CardDescription>
          Where your films and TV shows are, as Tailarr sees them. Tailarr uses the same /data
          folder as Radarr and Sonarr, so these normally match their root folders.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isPending && <Skeleton className="h-40 w-full" />}
        {settings.isError && <p className="text-sm text-destructive">{settings.error.message}</p>}
        {settings.data && <FolderForm initial={settings.data} />}
      </CardContent>
    </Card>
  );
}
