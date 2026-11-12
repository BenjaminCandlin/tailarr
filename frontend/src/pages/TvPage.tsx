import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LayoutGrid, List, RefreshCw, Search, SearchX, Tv, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { MediaBadges } from "@/components/MediaBadges";
import { PageHeader } from "@/components/PageHeader";
import { Poster } from "@/components/Poster";
import { PosterPlaceholderGrid } from "@/components/PosterPlaceholderGrid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type Show, type ShowList } from "@/lib/api";
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

type FilterKey = "all" | "dv" | "hdr" | "4k";

const FILTERS: { key: FilterKey; label: string; test: (show: Show) => boolean }[] = [
  { key: "all", label: "All shows", test: () => true },
  { key: "dv", label: "Has Dolby Vision", test: (s) => s.media.hdr.includes(DV) },
  { key: "hdr", label: "Any HDR", test: (s) => s.media.hdr.length > 0 },
  { key: "4k", label: "4K", test: (s) => s.media.resolution === "4K" },
];

const VIEW_KEY = "tailarr-tv-view";

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

function sortShows(shows: Show[], sort: SortKey): Show[] {
  if (sort === "title") return shows; // the server sends them by title already
  const sorted = [...shows];
  if (sort === "added") sorted.sort((a, b) => b.added_at.localeCompare(a.added_at));
  if (sort === "size") sorted.sort((a, b) => b.size - a.size);
  return sorted;
}

function showMeta(show: Show): string {
  const seasons = show.season_count > 0 ? plural(show.season_count, "season") : null;
  return [seasons, plural(show.episode_count, "episode")].filter(Boolean).join(" · ");
}

function ShowGrid({ shows }: { shows: Show[] }) {
  return (
    <ul
      aria-label="Shows"
      className="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8"
    >
      {shows.map((show) => (
        <li key={show.id}>
          <Link to={`/tv/shows/${show.id}`} className="group block rounded-lg">
            <div className="relative">
              <Poster
                src={show.poster_url}
                title={show.title}
                className="transition group-hover:border-primary group-hover:shadow-lg"
              />
              <div className="absolute top-2 right-2 left-2 flex flex-wrap gap-1">
                <MediaBadges media={show.media} overlay />
              </div>
            </div>
            <p className="mt-2 line-clamp-2 text-sm leading-snug font-medium [overflow-wrap:anywhere] group-hover:text-primary">
              {show.title}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">{showMeta(show)}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ShowRows({ shows }: { shows: Show[] }) {
  return (
    <ul aria-label="Shows" className="divide-y overflow-hidden rounded-lg border bg-card">
      {shows.map((show) => (
        <li key={show.id}>
          <Link
            to={`/tv/shows/${show.id}`}
            className="flex min-h-16 items-center gap-3 px-3 py-2 hover:bg-muted"
          >
            <Poster src={show.poster_url} title={show.title} compact className="w-10 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{show.title}</p>
              <p className="truncate text-xs text-muted-foreground">
                {showMeta(show)}
                <span className="hidden sm:inline"> · Latest {formatDate(show.added_at)}</span>
              </p>
              <span className="mt-1 flex gap-1 sm:hidden">
                <MediaBadges media={show.media} />
              </span>
            </div>
            <span className="hidden sm:flex sm:gap-1">
              <MediaBadges media={show.media} />
            </span>
            <span className="w-20 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
              {formatSize(show.size)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

const SELECT =
  "h-11 min-w-0 flex-1 cursor-pointer rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm";

function ScanLine({ data }: { data: ShowList }) {
  const { scan, reading } = data;
  if (scan.running || !scan.finished_at) return null;
  if (reading.running && reading.total > 0) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Reading file details… {reading.done.toLocaleString()} of {reading.total.toLocaleString()}
      </p>
    );
  }
  return <p className="text-sm text-muted-foreground">Last checked {timeAgo(scan.finished_at)}</p>;
}

function TvContent({ data }: { data: ShowList }) {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useStoredView();
  const query = params.get("q") ?? "";
  const sortParam = params.get("sort");
  const sort: SortKey = SORTS.some((s) => s.key === sortParam) ? (sortParam as SortKey) : "title";
  const filter = FILTERS.find((f) => f.key === params.get("show")) ?? FILTERS[0];

  function update(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const shown = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return sortShows(
      data.shows.filter((show) => {
        const haystack = fold(`${show.title} ${show.year ?? ""} ${show.folder_name}`);
        return filter.test(show) && words.every((w) => haystack.includes(w));
      }),
      sort,
    );
  }, [data.shows, query, sort, filter]);

  const { scan } = data;
  if (data.shows.length === 0) {
    if (scan.error) {
      return (
        <EmptyState icon={AlertTriangle} title="Tailarr can't see your TV shows">
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
            <EmptyState icon={RefreshCw} title="Looking for your TV shows…">
              <p>This only reads the folder names, so it's quick. Your shows will appear here.</p>
            </EmptyState>
          </div>
        </div>
      );
    }
    return (
      <EmptyState icon={Tv} title="No TV shows found">
        <p>
          Tailarr looked in{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 break-all text-foreground">
            {data.root}
          </code>{" "}
          and found no shows. It expects one folder per show with season folders inside, the way
          Sonarr organises them, for example{" "}
          <span className="text-foreground">Show (2020)/Season 01/Show (2020) - S01E01.mkv</span>.
        </p>
        <Button asChild variant="secondary" className="mt-4">
          <Link to="/settings">Check the TV folder in Settings</Link>
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
            {scan.error} The shows below are from the last time it worked.
          </p>
        </div>
      )}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-[1_1_16rem]">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            value={query}
            onChange={(e) => update("q", e.target.value, "")}
            placeholder="Search shows"
            aria-label="Search shows"
            className="pl-9"
          />
        </div>
        <div className="flex flex-[1_1_100%] flex-wrap items-center gap-3 sm:flex-none">
          <label className="sr-only" htmlFor="tv-filter">
            Show
          </label>
          <select
            id="tv-filter"
            value={filter.key}
            onChange={(e) => update("show", e.target.value, "all")}
            className={cn(SELECT, filter.key !== "all" && "border-primary text-primary")}
          >
            {FILTERS.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="tv-sort">
            Sort shows
          </label>
          <select
            id="tv-sort"
            value={sort}
            onChange={(e) => update("sort", e.target.value, "title")}
            className={SELECT}
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          <div
            role="group"
            aria-label="Show TV shows as"
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
                onClick={() => setView(key)}
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
      {(query || filter.key !== "all") && shown.length > 0 && (
        <p className="mb-3 text-sm text-muted-foreground" role="status">
          {plural(shown.length, "show")} found
        </p>
      )}
      {shown.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={query ? `No shows match “${query}”` : `No shows: ${filter.label}`}
        >
          <p>
            {query
              ? "Try fewer words, or check the spelling."
              : "None of your shows match this filter."}
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
                Show all shows
              </Button>
            )}
          </div>
        </EmptyState>
      ) : view === "grid" ? (
        <ShowGrid shows={shown} />
      ) : (
        <ShowRows shows={shown} />
      )}
    </>
  );
}

export function TvPage() {
  const queryClient = useQueryClient();
  const shows = useQuery({
    queryKey: ["tv"],
    queryFn: api.shows,
    refetchInterval: (q) =>
      q.state.data?.scan.running ? 2000 : q.state.data?.reading.running ? 5000 : false,
  });
  const rescan = useMutation({
    mutationFn: api.rescanTv,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["tv"] }),
  });
  const data = shows.data;
  const scanning = rescan.isPending || Boolean(data?.scan.running);
  const episodes = data?.shows.reduce((sum, s) => sum + s.episode_count, 0) ?? 0;
  const total = data?.shows.reduce((sum, s) => sum + s.size, 0) ?? 0;

  return (
    <>
      <PageHeader
        title="TV"
        description={
          data && data.shows.length > 0
            ? `${plural(data.shows.length, "show")} · ${plural(episodes, "episode")} · ${formatSize(total)}`
            : "Shows, seasons and episodes in your TV folder."
        }
        actions={
          <div className="flex flex-wrap items-center gap-3">
            {data && <ScanLine data={data} />}
            <Button
              variant="secondary"
              onClick={() => rescan.mutate()}
              disabled={scanning}
              title="Look for new, changed or removed episodes now"
            >
              <RefreshCw className={cn(scanning && "animate-spin")} aria-hidden />
              {scanning ? "Checking…" : "Check for new episodes"}
            </Button>
          </div>
        }
      />
      {shows.isPending && <PosterPlaceholderGrid />}
      {shows.isError && (
        <EmptyState icon={AlertTriangle} title="Couldn't load your TV shows">
          <p>{shows.error.message}</p>
          <Button variant="secondary" className="mt-4" onClick={() => shows.refetch()}>
            Try again
          </Button>
        </EmptyState>
      )}
      {data && <TvContent data={data} />}
    </>
  );
}
