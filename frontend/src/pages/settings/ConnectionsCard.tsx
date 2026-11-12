import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ClipboardCopy, PlugZap, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { StatusIcon } from "@/components/StatusIcon";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  api,
  type ConnectionTest,
  type Connections,
  type ConnectionsInput,
  type ServiceName,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const SERVICES: {
  key: ServiceName;
  label: string;
  example: string;
  keyLabel: string;
  keyHelp: string;
  purpose: string;
}[] = [
  {
    key: "radarr",
    label: "Radarr",
    example: "http://radarr:7878",
    keyLabel: "API key",
    keyHelp: "In Radarr: Settings → General → Security → API Key.",
    purpose: "Film titles and posters, and keeping Tailarr's copies in step with upgrades.",
  },
  {
    key: "sonarr",
    label: "Sonarr",
    example: "http://sonarr:8989",
    keyLabel: "API key",
    keyHelp: "In Sonarr: Settings → General → Security → API Key.",
    purpose: "Show titles and posters, and keeping Tailarr's copies in step with upgrades.",
  },
  {
    key: "plex",
    label: "Plex",
    example: "http://plex:32400",
    keyLabel: "Plex token",
    keyHelp:
      "Plex's help article “Finding an authentication token” explains where to find it (open any item → Get Info → View XML; the token is at the end of the address).",
    purpose: "Asking Plex to show new copies and changed tracks straight away.",
  },
];

type Draft = Record<ServiceName, { url: string; key: string }>;

function ServiceBlock({
  service,
  saved,
  draft,
  onChange,
}: {
  service: (typeof SERVICES)[number];
  saved: Connections["radarr"];
  draft: { url: string; key: string };
  onChange: (value: { url: string; key: string }) => void;
}) {
  const [result, setResult] = useState<ConnectionTest | null>(null);
  const test = useMutation({
    mutationFn: () => api.testConnection(service.key, draft.url, draft.key),
    onSuccess: setResult,
  });
  const connected = Boolean(saved.url && saved.has_key);
  return (
    <section
      className="flex flex-col gap-3 rounded-xl border p-4"
      aria-labelledby={`${service.key}-title`}
      data-testid={`connection-${service.key}`}
    >
      <div className="flex items-start gap-3">
        <StatusIcon status={connected ? "ok" : "optional"} />
        <div className="min-w-0">
          <h3 id={`${service.key}-title`} className="font-medium">
            {service.label}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {connected ? "Connected" : "Not connected (optional)"}
            </span>
          </h3>
          <p className="text-sm text-muted-foreground">{service.purpose}</p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${service.key}-url`} className="text-sm font-medium">
            Address
          </label>
          <Input
            id={`${service.key}-url`}
            value={draft.url}
            placeholder={service.example}
            onChange={(e) => {
              onChange({ ...draft, url: e.target.value });
              setResult(null);
            }}
            spellCheck={false}
            autoCapitalize="off"
          />
          <p className="text-xs text-muted-foreground">
            On a custom Docker network, use the container name, for example {service.example}.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${service.key}-key`} className="text-sm font-medium">
            {service.keyLabel}
          </label>
          <Input
            id={`${service.key}-key`}
            type="password"
            value={draft.key}
            placeholder={saved.has_key ? "Saved (leave empty to keep it)" : ""}
            onChange={(e) => {
              onChange({ ...draft, key: e.target.value });
              setResult(null);
            }}
            autoComplete="off"
            spellCheck={false}
          />
          <p className="text-xs text-muted-foreground">{service.keyHelp}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={() => test.mutate()}
          disabled={!draft.url || test.isPending}
        >
          <PlugZap aria-hidden />
          {test.isPending ? "Testing…" : `Test ${service.label}`}
        </Button>
        {result && (
          <p
            role={result.ok ? "status" : "alert"}
            className={cn("text-sm", result.ok ? "text-success" : "text-destructive")}
          >
            {result.message}
          </p>
        )}
        {test.isError && (
          <p role="alert" className="text-sm text-destructive">
            {test.error.message}
          </p>
        )}
      </div>
      {result && !result.ok && <TechnicalDetails details={result.details} />}
    </section>
  );
}

function Option({
  id,
  checked,
  onChange,
  title,
  text,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  text: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        aria-describedby={`${id}-help`}
      />
      <div className="pt-1.5 md:pt-1">
        <label htmlFor={id} className="cursor-pointer text-sm font-medium">
          {title}
        </label>
        <p id={`${id}-help`} className="text-xs text-muted-foreground">
          {text}
        </p>
      </div>
    </div>
  );
}

function CopyField({ label, value, id }: { label: string; value: string; id: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="flex gap-2">
        <Input
          id={id}
          readOnly
          value={value}
          onFocus={(e) => e.target.select()}
          className="min-w-0 font-mono text-xs md:text-xs"
        />
        <Button
          type="button"
          variant="secondary"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 2000);
            } catch {
              document.getElementById(id)?.focus();
            }
          }}
          aria-label={`Copy the ${label}`}
        >
          {copied ? <Check aria-hidden /> : <ClipboardCopy aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

function Webhooks({ data }: { data: Connections }) {
  const queryClient = useQueryClient();
  const renew = useMutation({
    mutationFn: api.newWebhookSecret,
    onSuccess: (saved) => queryClient.setQueryData(["settings", "connections"], saved),
  });
  const here = typeof window === "undefined" ? "" : window.location.origin;
  return (
    <section className="flex flex-col gap-3 rounded-xl border p-4" aria-labelledby="webhooks-title">
      <h3 id="webhooks-title" className="font-medium">
        Messages from Radarr and Sonarr (webhooks)
      </h3>
      <p className="text-sm text-muted-foreground">
        So Tailarr hears about new films and episodes, upgrades, deletes and renames straight away.
        In Radarr: <span className="text-foreground">Settings → Connect → + → Webhook</span>. Name
        it “Tailarr”, tick <span className="text-foreground">On File Import</span>,{" "}
        <span className="text-foreground">On File Upgrade</span>,{" "}
        <span className="text-foreground">On Rename</span> and the{" "}
        <span className="text-foreground">On … File Delete</span> options, paste the address below,
        method POST, then Save. Do the same in Sonarr with its address.
      </p>
      <CopyField
        id="webhook-radarr"
        label="Radarr webhook address"
        value={`http://tailarr:8484${data.webhook_paths.radarr}`}
      />
      <CopyField
        id="webhook-sonarr"
        label="Sonarr webhook address"
        value={`http://tailarr:8484${data.webhook_paths.sonarr}`}
      />
      <p className="text-xs text-muted-foreground">
        These use Tailarr's container name, which works when Radarr and Sonarr are on the same
        custom Docker network. Otherwise replace the start with the address you use for Tailarr (
        {here || "this page's address"}). The secret at the end stops anyone else sending messages.
      </p>
      <div>
        <Button
          type="button"
          variant="ghost"
          onClick={() => renew.mutate()}
          disabled={renew.isPending}
        >
          <RefreshCw aria-hidden />
          Make a new secret
        </Button>
        <p className="text-xs text-muted-foreground">
          The old addresses stop working, so paste the new ones into Radarr and Sonarr.
        </p>
      </div>
    </section>
  );
}

function Recent() {
  const activity = useQuery({
    queryKey: ["activity", "connections"],
    queryFn: () => api.activity({ limit: 5 }),
    refetchInterval: 15_000,
  });
  const entries = activity.data ?? [];
  if (entries.length === 0) return null;
  return (
    <section aria-labelledby="recent-title" className="flex flex-col gap-2">
      <h3 id="recent-title" className="text-sm font-medium">
        Recently
      </h3>
      <ul className="flex flex-col gap-1.5 text-sm">
        {entries.map((entry) => (
          <li key={entry.id} className="flex gap-2">
            <StatusIcon status={entry.ok ? "ok" : "problem"} />
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {entry.message}{" "}
              <span className="text-xs text-muted-foreground">{timeAgo(entry.at)}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ConnectionsForm({ data }: { data: Connections }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>({
    radarr: { url: data.radarr.url, key: "" },
    sonarr: { url: data.sonarr.url, key: "" },
    plex: { url: data.plex.url, key: "" },
  });
  const [options, setOptions] = useState({
    plex_refresh: data.plex_refresh,
    arr_rescan: data.arr_rescan,
    tidy_copies: data.tidy_copies,
  });
  const save = useMutation({
    mutationFn: (body: ConnectionsInput) => api.saveConnections(body),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings", "connections"], saved);
      setDraft((d) => ({
        radarr: { ...d.radarr, key: "" },
        sonarr: { ...d.sonarr, key: "" },
        plex: { ...d.plex, key: "" },
      }));
      // Titles and posters arrive in the background.
      window.setTimeout(() => {
        for (const key of ["films", "tv", "settings"]) {
          void queryClient.invalidateQueries({ queryKey: [key] });
        }
      }, 3000);
    },
  });
  const sync = useMutation({
    mutationFn: api.syncConnections,
    onSettled: () =>
      window.setTimeout(() => {
        for (const key of ["films", "tv", "settings"]) {
          void queryClient.invalidateQueries({ queryKey: [key] });
        }
      }, 3000),
  });
  const changed =
    SERVICES.some((s) => draft[s.key].url !== data[s.key].url || draft[s.key].key !== "") ||
    options.plex_refresh !== data.plex_refresh ||
    options.arr_rescan !== data.arr_rescan ||
    options.tidy_copies !== data.tidy_copies;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const service = (key: ServiceName) => ({
      url: draft[key].url,
      ...(draft[key].key ? { api_key: draft[key].key } : {}),
    });
    save.mutate({
      radarr: service("radarr"),
      sonarr: service("sonarr"),
      plex: service("plex"),
      ...options,
    });
  }

  const { sync: status } = data;
  const anyArr = Boolean(
    (data.radarr.url && data.radarr.has_key) || (data.sonarr.url && data.sonarr.has_key),
  );
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      {SERVICES.map((service) => (
        <ServiceBlock
          key={service.key}
          service={service}
          saved={data[service.key]}
          draft={draft[service.key]}
          onChange={(value) => setDraft((d) => ({ ...d, [service.key]: value }))}
        />
      ))}
      <section className="flex flex-col gap-3" aria-label="What Tailarr does with them">
        <Option
          id="plex-refresh"
          checked={options.plex_refresh}
          onChange={(v) => setOptions((o) => ({ ...o, plex_refresh: v }))}
          title="Ask Plex to refresh after each job"
          text="New copies then show up as versions, and changed tracks are noticed, without waiting for Plex's own scan."
        />
        <Option
          id="arr-rescan"
          checked={options.arr_rescan}
          onChange={(v) => setOptions((o) => ({ ...o, arr_rescan: v }))}
          title="Ask Radarr/Sonarr to rescan after Tailarr changes an original"
          text="Only after changing track settings in place or replacing an original, so their notes about the file stay right. Not needed for new copies (they ignore those)."
        />
        <Option
          id="tidy-copies"
          checked={options.tidy_copies}
          onChange={(v) => setOptions((o) => ({ ...o, tidy_copies: v }))}
          title="Keep Tailarr's copies in step with Radarr and Sonarr"
          text="When they upgrade or delete a film or episode, Tailarr's copies of the old file go to the recycle folder (they're from the old release). When they rename one, its copies are renamed to match. Needs the webhooks below."
        />
      </section>
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
          {save.isPending ? "Saving…" : "Save connections"}
        </Button>
        {save.isSuccess && !changed && (
          <p role="status" className="text-sm text-success">
            Saved.
          </p>
        )}
      </div>
      {anyArr && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-muted px-3 py-2.5 text-sm">
          <p className="min-w-0 flex-1" data-testid="sync-status">
            {status.running
              ? "Getting titles and posters from Radarr and Sonarr…"
              : status.finished_at
                ? `Titles and posters: ${[
                    status.films !== null && `${status.films} films`,
                    status.shows !== null && `${status.shows} shows`,
                  ]
                    .filter(Boolean)
                    .join(" and ")} matched, ${timeAgo(status.finished_at)}.`
                : "Titles and posters haven't been fetched yet."}
            {status.errors &&
              Object.values(status.errors).map((e) => (
                <span key={e} className="block text-destructive">
                  {e}
                </span>
              ))}
          </p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => sync.mutate()}
            disabled={sync.isPending || status.running}
          >
            <RefreshCw aria-hidden />
            Fetch them now
          </Button>
        </div>
      )}
      <Webhooks data={data} />
      <Recent />
    </form>
  );
}

export function ConnectionsCard() {
  const connections = useQuery({
    queryKey: ["settings", "connections"],
    queryFn: api.connections,
    refetchInterval: (q) => (q.state.data?.sync.running ? 2000 : false),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Radarr, Sonarr and Plex</CardTitle>
        <CardDescription>
          All optional. Connecting them gives proper titles and posters, keeps Tailarr's copies tidy
          when files are upgraded or renamed, and lets Plex show changes straight away. Keys are
          kept only in Tailarr's database in /config.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {connections.isPending && <Skeleton className="h-64 w-full" />}
        {connections.isError && (
          <p role="alert" className="text-sm text-destructive">
            {connections.error.message}
          </p>
        )}
        {connections.data && <ConnectionsForm data={connections.data} />}
      </CardContent>
    </Card>
  );
}
