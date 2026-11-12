import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Search, Trash2 } from "lucide-react";

import { api, type LibrarySettings, type MappingTest, type PathMapping } from "@/lib/api";
import { cn } from "@/lib/utils";

function FolderForm({ initial }: { initial: LibrarySettings }) {
  const queryClient = useQueryClient();
  const [movies, setMovies] = useState(initial.movies_dir);
  const [tv, setTv] = useState(initial.tv_dir);
  const [mappings, setMappings] = useState<PathMapping[]>(initial.path_mappings);
  const save = useMutation({
    mutationFn: api.saveLibrarySettings,
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings", "library"], saved);
      void queryClient.invalidateQueries({ queryKey: ["health"] });
      void queryClient.invalidateQueries({ queryKey: ["films"] });
    },
  });
  const cleanMappings = mappings.filter((m) => m.remote.trim() || m.local.trim());
  const changed =
    movies !== initial.movies_dir ||
    tv !== initial.tv_dir ||
    JSON.stringify(cleanMappings) !== JSON.stringify(initial.path_mappings);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ movies_dir: movies, tv_dir: tv, path_mappings: cleanMappings });
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
      <PathMappings mappings={mappings} onChange={setMappings} />
    </form>
  );
}

function PathMappings({
  mappings,
  onChange,
}: {
  mappings: PathMapping[];
  onChange: (mappings: PathMapping[]) => void;
}) {
  const [probe, setProbe] = useState("");
  const [result, setResult] = useState<MappingTest | null>(null);
  const test = useMutation({ mutationFn: () => api.testPathMapping(probe), onSuccess: setResult });
  const set = (index: number, change: Partial<PathMapping>) =>
    onChange(mappings.map((m, i) => (i === index ? { ...m, ...change } : m)));
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border p-3">
      <legend className="px-1 text-sm font-medium">Path mapping</legend>
      <p className="text-xs text-muted-foreground">
        Only needed if Radarr, Sonarr or Plex see your files under a different path from Tailarr
        (for example Plex sees <span className="font-mono">/media/movies</span> where Tailarr sees{" "}
        <span className="font-mono">/data/media/movies</span>). With the same /data folder
        everywhere, leave this empty.
      </p>
      {mappings.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Path mappings">
          {mappings.map((mapping, index) => (
            <li key={index} className="flex flex-col gap-2 md:flex-row md:items-end">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <label htmlFor={`map-remote-${index}`} className="text-xs font-medium">
                  Path in Radarr, Sonarr or Plex
                </label>
                <Input
                  id={`map-remote-${index}`}
                  value={mapping.remote}
                  placeholder="/movies"
                  onChange={(e) => set(index, { remote: e.target.value })}
                  spellCheck={false}
                  autoCapitalize="off"
                />
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <label htmlFor={`map-local-${index}`} className="text-xs font-medium">
                  The same folder in Tailarr
                </label>
                <Input
                  id={`map-local-${index}`}
                  value={mapping.local}
                  placeholder="/data/media/movies"
                  onChange={(e) => set(index, { local: e.target.value })}
                  spellCheck={false}
                  autoCapitalize="off"
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onChange(mappings.filter((_, i) => i !== index))}
                aria-label={`Remove the path mapping ${mapping.remote || index + 1}`}
              >
                <Trash2 aria-hidden />
                <span className="md:sr-only">Remove</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => onChange([...mappings, { remote: "", local: "" }])}
        >
          <Plus aria-hidden />
          Add a path mapping
        </Button>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="map-probe" className="text-xs font-medium">
          Test a path (as Radarr, Sonarr or Plex show it; uses the saved mappings)
        </label>
        <div className="flex gap-2">
          <Input
            id="map-probe"
            value={probe}
            placeholder="/movies/Film (2020)"
            onChange={(e) => {
              setProbe(e.target.value);
              setResult(null);
            }}
            spellCheck={false}
            autoCapitalize="off"
            className="min-w-0"
          />
          <Button
            type="button"
            variant="secondary"
            onClick={() => test.mutate()}
            disabled={!probe.trim() || test.isPending}
          >
            <Search aria-hidden />
            Test
          </Button>
        </div>
        {result && (
          <p
            role="status"
            className={cn(
              "text-sm [overflow-wrap:anywhere]",
              result.exists && result.inside_library ? "text-success" : "text-destructive",
            )}
          >
            {result.message} <span className="text-muted-foreground">({result.path})</span>
          </p>
        )}
      </div>
    </fieldset>
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
