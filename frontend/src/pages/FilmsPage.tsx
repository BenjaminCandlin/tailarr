import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Clapperboard,
  LayoutGrid,
  List,
  RefreshCw,
  Search,
  SearchX,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { GettingStarted } from "@/components/GettingStarted";
import { MediaBadges } from "@/components/MediaBadges";
import { PageHeader } from "@/components/PageHeader";
import { Poster } from "@/components/Poster";
import { PosterPlaceholderGrid } from "@/components/PosterPlaceholderGrid";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type Film, type FilmList } from "@/lib/api";
import { fold, formatDate, formatSize, plural, timeAgo } from "@/lib/format";
import { DV } from "@/lib/hdr";
import { cn } from "@/lib/utils";

type SortKey = "title" | "added" | "size";
type View = "grid" | "list";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "title", label: "Title (A–Z)" },
  { key: "added", label: "Recently added" },
  { key: "size", label: "Largest first" },
];

type FilterKey = "all" | "dv" | "hdr10plus" | "hdr" | "sdr" | "4k";

const FILTERS: { key: FilterKey; label: string; test: (film: Film) => boolean }[] = [
  { key: "all", label: "All films", test: () => true },
  { key: "dv", label: "Has Dolby Vision", test: (f) => f.media.hdr.includes(DV) },
  { key: "hdr10plus", label: "Has HDR10+", test: (f) => f.media.hdr.includes("HDR10+") },
  { key: "hdr", label: "Any HDR", test: (f) => f.media.hdr.length > 0 },
  {
    key: "sdr",
    label: "No HDR",
    test: (f) => f.media.read && !f.media.error && f.media.hdr.length === 0,
  },
  { key: "4k", label: "4K", test: (f) => f.media.resolution === "4K" },
];

const VIEW_KEY = "tailarr-films-view";

function useStoredView(): [View, (view: View) => void] {
  const [view, setView] = useState<View>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid";
    } catch {
      return "grid";
    }
  });
  return [
    view,
    (next) => {
      setView(next);
      try {
        localStorage.setItem(VIEW_KEY, next);
      } catch {
        // Not remembered, but still works.
      }
    },
  ];
}

function sortFilms(films: Film[], sort: SortKey): Film[] {
  // The server already sends them by title (ignoring "The" and accents).
  if (sort === "title") return films;
  const sorted = [...films];
  if (sort === "added") sorted.sort((a, b) => b.added_at.localeCompare(a.added_at));
  if (sort === "size") sorted.sort((a, b) => b.size - a.size);
  return sorted;
}

function matches(film: Film, words: string[]): boolean {
  const haystack = fold(`${film.title} ${film.year ?? ""} ${film.folder_name}`);
  return words.every((word) => haystack.includes(word));
}

function filmMeta(film: Film): string {
  return [film.year, formatSize(film.size)].filter(Boolean).join(" · ");
}

function NotMkv({ film, overlay = false }: { film: Film; overlay?: boolean }) {
  if (film.is_mkv) return null;
  return (
    <Badge
      tone="warning"
      title="Tailarr can only change MKV files"
      className={cn(overlay && "shadow-sm ring-1 ring-black/10")}
    >
      Not MKV
    </Badge>
  );
}

function FilmGrid({ films }: { films: Film[] }) {
  return (
    <ul
      aria-label="Films"
      className="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8"
    >
      {films.map((film) => (
        <li key={film.id}>
          <Link to={`/films/${film.id}`} className="group block rounded-lg">
            <div className="relative">
              <Poster
                src={film.poster_url}
                title={film.title}
                className="transition group-hover:border-primary group-hover:shadow-lg"
              />
              <div className="absolute top-2 right-2 left-2 flex flex-wrap gap-1">
                <NotMkv film={film} overlay />
                <MediaBadges media={film.media} overlay />
              </div>
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-snug font-medium [overflow-wrap:anywhere] group-hover:text-primary">
              {film.title}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">{filmMeta(film)}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function FilmRows({ films }: { films: Film[] }) {
  return (
    <ul aria-label="Films" className="divide-y overflow-hidden rounded-lg border bg-card">
      {films.map((film) => (
        <li key={film.id}>
          <Link
            to={`/films/${film.id}`}
            className="flex min-h-16 items-center gap-3 px-3 py-2 hover:bg-muted"
          >
            <Poster src={film.poster_url} title={film.title} compact className="w-10 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{film.title}</p>
              <p className="truncate text-xs text-muted-foreground">
                {film.year ?? "Year unknown"}
                <span className="hidden sm:inline"> · Added {formatDate(film.added_at)}</span>
              </p>
              <span className="mt-1 flex gap-1 sm:hidden">
                <NotMkv film={film} />
                <MediaBadges media={film.media} />
              </span>
            </div>
            <span className="hidden sm:flex sm:gap-1">
              <NotMkv film={film} />
              <MediaBadges media={film.media} />
            </span>
            <span className="w-20 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
              {formatSize(film.size)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Toolbar({
  query,
  onQuery,
  sort,
  onSort,
  filter,
  onFilter,
  view,
  onView,
}: {
  query: string;
  onQuery: (q: string) => void;
  sort: SortKey;
  onSort: (s: SortKey) => void;
  filter: FilterKey;
  onFilter: (f: FilterKey) => void;
  view: View;
  onView: (v: View) => void;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3">
      <div className="relative min-w-0 flex-[1_1_16rem]">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search films"
          aria-label="Search films"
          className="pl-9"
        />
      </div>
      <div className="flex flex-[1_1_100%] flex-wrap items-center gap-3 sm:flex-none">
        <label className="sr-only" htmlFor="film-filter">
          Show
        </label>
        <select
          id="film-filter"
          value={filter}
          onChange={(e) => onFilter(e.target.value as FilterKey)}
          className={cn(
            "h-11 min-w-0 flex-1 cursor-pointer rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm",
            filter !== "all" && "border-primary text-primary",
          )}
        >
          {FILTERS.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="film-sort">
          Sort films
        </label>
        <select
          id="film-sort"
          value={sort}
          onChange={(e) => onSort(e.target.value as SortKey)}
          className="h-11 min-w-0 flex-1 cursor-pointer rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm"
        >
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <div
          role="group"
          aria-label="Show films as"
          className="flex rounded-lg border bg-card p-0.5"
        >
          {(
            [
              ["grid", LayoutGrid, "Posters"],
              ["list", List, "List"],
            ] as const
          ).map(([key, Icon, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => onView(key)}
              aria-pressed={view === key}
              aria-label={label}
              title={label}
              className={cn(
                "flex size-10 cursor-pointer items-center justify-center rounded-md md:size-9",
                view === key
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-5" aria-hidden />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ScanLine({ data }: { data: FilmList }) {
  const { scan, reading } = data;
  if (scan.running || !scan.finished_at) return null; // the button says "Checking…"
  if (reading.running && reading.total > 0) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Reading film details… {reading.done.toLocaleString()} of {reading.total.toLocaleString()}
      </p>
    );
  }
  return <p className="text-sm text-muted-foreground">Last checked {timeAgo(scan.finished_at)}</p>;
}

function FilmsContent({ data }: { data: FilmList }) {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useStoredView();
  const query = params.get("q") ?? "";
  const sortParam = params.get("sort");
  const sort: SortKey = SORTS.some((s) => s.key === sortParam) ? (sortParam as SortKey) : "title";
  const filterParam = params.get("show");
  const filter = FILTERS.find((f) => f.key === filterParam) ?? FILTERS[0];

  function update(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const shown = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return sortFilms(
      data.films.filter((film) => filter.test(film) && matches(film, words)),
      sort,
    );
  }, [data.films, query, sort, filter]);
  const unread = data.films.filter((f) => !f.media.read).length;

  const { scan } = data;

  if (data.films.length === 0) {
    if (scan.error) {
      return (
        <EmptyState icon={AlertTriangle} title="Tailarr can't see your films">
          <p>{scan.error}</p>
          <Button asChild variant="secondary" className="mt-4">
            <Link to="/settings">Open Settings</Link>
          </Button>
        </EmptyState>
      );
    }
    if (scan.running || !scan.finished_at) {
      return (
        <div className="relative">
          <PosterPlaceholderGrid />
          <div className="absolute inset-0 flex items-start justify-center bg-gradient-to-b from-background/40 via-background/80 to-background pt-6 md:pt-16 [&>*]:w-full [&>*]:max-w-xl">
            <EmptyState icon={RefreshCw} title="Looking for your films…">
              <p>This only reads the folder names, so it's quick. Your films will appear here.</p>
            </EmptyState>
          </div>
        </div>
      );
    }
    return (
      <EmptyState icon={Clapperboard} title="No films found">
        <p>
          Tailarr looked in{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 break-all text-foreground">
            {data.root}
          </code>{" "}
          and found no films. It expects one folder per film, the way Radarr organises them, for
          example <span className="text-foreground">Film Title (2020)/Film Title (2020).mkv</span>.
        </p>
        <Button asChild variant="secondary" className="mt-4">
          <Link to="/settings">Check the Films folder in Settings</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <>
      {scan.error && (
        <div
          role="alert"
          className="mb-5 flex gap-3 rounded-lg border border-warning/40 bg-warning-soft px-4 py-3 text-sm"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <p>
            <span className="font-medium">The last check didn't work. </span>
            {scan.error} The films below are from the last time it worked.
          </p>
        </div>
      )}
      <Toolbar
        query={query}
        onQuery={(q) => update("q", q, "")}
        sort={sort}
        onSort={(s) => update("sort", s, "title")}
        filter={filter.key}
        onFilter={(f) => update("show", f, "all")}
        view={view}
        onView={setView}
      />
      {(query || filter.key !== "all") && shown.length > 0 && (
        <p className="mb-3 text-sm text-muted-foreground" role="status">
          {plural(shown.length, "film")} found
        </p>
      )}
      {filter.key !== "all" && unread > 0 && (
        <p className="mb-3 text-sm text-muted-foreground">
          Tailarr is still reading the details of {plural(unread, "film")}. They'll appear here if
          they match.
        </p>
      )}
      {shown.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={query ? `No films match “${query}”` : `No films: ${filter.label}`}
        >
          <p>
            {query
              ? "Try fewer words, or check the spelling."
              : "None of your films match this filter."}
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {query && (
              <Button variant="secondary" onClick={() => update("q", "", "")}>
                <X aria-hidden />
                Clear search
              </Button>
            )}
            {filter.key !== "all" && (
              <Button variant="secondary" onClick={() => update("show", "", "all")}>
                <X aria-hidden />
                Show all films
              </Button>
            )}
          </div>
        </EmptyState>
      ) : view === "grid" ? (
        <FilmGrid films={shown} />
      ) : (
        <FilmRows films={shown} />
      )}
    </>
  );
}

export function FilmsPage() {
  const queryClient = useQueryClient();
  const films = useQuery({
    queryKey: ["films"],
    queryFn: api.films,
    // While Tailarr is looking for films, check back every 2 seconds; while it's reading
    // film details (slower, file by file), every 5 seconds.
    refetchInterval: (q) =>
      q.state.data?.scan.running ? 2000 : q.state.data?.reading.running ? 5000 : false,
  });
  const rescan = useMutation({
    mutationFn: api.rescanFilms,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["films"] }),
  });
  const data = films.data;
  const scanning = rescan.isPending || Boolean(data?.scan.running);
  const total = data?.films.reduce((sum, f) => sum + f.size, 0) ?? 0;

  return (
    <>
      <PageHeader
        title="Films"
        description={
          data && data.films.length > 0
            ? `${plural(data.films.length, "film")} · ${formatSize(total)}`
            : "Everything in your Films folder."
        }
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {data && <ScanLine data={data} />}
            <Button
              variant="secondary"
              onClick={() => rescan.mutate()}
              disabled={scanning}
              title="Look for new, changed or removed films now"
            >
              <RefreshCw className={cn(scanning && "animate-spin")} aria-hidden />
              {scanning ? "Checking…" : "Check for new films"}
            </Button>
          </div>
        }
      />
      <GettingStarted />
      {films.isPending && <PosterPlaceholderGrid />}
      {films.isError && (
        <EmptyState icon={AlertTriangle} title="Couldn't load your films">
          <p>{films.error.message}</p>
          <Button variant="secondary" className="mt-4" onClick={() => films.refetch()}>
            Try again
          </Button>
        </EmptyState>
      )}
      {data && <FilmsContent data={data} />}
    </>
  );
}
