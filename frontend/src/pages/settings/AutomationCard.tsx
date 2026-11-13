import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, type Automation } from "@/lib/api";
import { timeAgo } from "@/lib/format";

function AutomationForm({ initial }: { initial: Automation }) {
  const queryClient = useQueryClient();
  const [settle, setSettle] = useState(String(initial.settle_seconds));
  const [watch, setWatch] = useState(initial.watch_folders);
  const [rescan, setRescan] = useState(String(initial.rescan_minutes));
  const save = useMutation({
    mutationFn: () =>
      api.saveAutomation({
        settle_seconds: Number(settle),
        watch_folders: watch,
        rescan_minutes: Number(rescan),
      }),
    onSuccess: (saved) => queryClient.setQueryData(["settings", "automation"], saved),
  });
  const settleOk =
    Number.isInteger(Number(settle)) && Number(settle) >= 0 && Number(settle) <= 3600;
  const rescanOk =
    Number.isInteger(Number(rescan)) && Number(rescan) >= 5 && Number(rescan) <= 1440;
  const changed =
    Number(settle) !== initial.settle_seconds ||
    watch !== initial.watch_folders ||
    Number(rescan) !== initial.rescan_minutes;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (settleOk && rescanOk) save.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="settle-seconds" className="text-sm font-medium">
          Wait until a new file has stopped changing for (seconds)
        </label>
        <Input
          id="settle-seconds"
          type="number"
          inputMode="numeric"
          min={0}
          max={3600}
          value={settle}
          onChange={(e) => setSettle(e.target.value)}
          aria-invalid={!settleOk || undefined}
          className="max-w-32"
        />
        <p className="text-xs text-muted-foreground">
          So rules never touch a file that's still being copied. MKVToolNix must also be able to
          read it. 120 seconds (2 minutes) is a safe choice.
        </p>
      </div>
      <div className="flex items-start gap-3">
        <Switch
          id="watch-folders"
          checked={watch}
          onCheckedChange={setWatch}
          aria-describedby="watch-folders-help"
        />
        <div className="pt-1.5 md:pt-1">
          <label htmlFor="watch-folders" className="cursor-pointer text-sm font-medium">
            Also watch the Films and TV folders for new files
          </label>
          <p id="watch-folders-help" className="text-xs text-muted-foreground">
            Only needed if Radarr and Sonarr can't send webhooks (see “Radarr, Sonarr and Plex”
            above, which is the better way). Files already there when you switch this on are left
            alone.
          </p>
        </div>
      </div>
      {watch && (
        <div className="flex flex-col gap-1.5 md:pl-15">
          <label htmlFor="rescan-minutes" className="text-sm font-medium">
            Also look through the folders every (minutes)
          </label>
          <Input
            id="rescan-minutes"
            type="number"
            inputMode="numeric"
            min={5}
            max={1440}
            value={rescan}
            onChange={(e) => setRescan(e.target.value)}
            aria-invalid={!rescanOk || undefined}
            className="max-w-32"
          />
          <p className="text-xs text-muted-foreground">
            Unraid's shares don't always report new files, so Tailarr also checks regularly.
          </p>
        </div>
      )}
      {initial.waiting.length > 0 && (
        <div className="rounded-lg bg-muted px-3 py-2 text-sm" data-testid="automation-waiting">
          <p className="font-medium">Waiting until they've finished copying:</p>
          <ul className="list-disc pl-5">
            {initial.waiting.map((item) => (
              <li key={item.file} className="[overflow-wrap:anywhere]">
                {item.file}{" "}
                <span className="text-muted-foreground">
                  ({item.reason}, {timeAgo(item.since)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {save.isError && (
        <p
          role="alert"
          className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
        >
          {save.error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!changed || !settleOk || !rescanOk || save.isPending}>
          {save.isPending ? "Saving…" : "Save automatic rules"}
        </Button>
        {save.isSuccess && !changed && (
          <p role="status" className="text-sm text-success">
            Saved.
          </p>
        )}
        <Link to="/activity" className="text-sm text-primary hover:underline">
          Open the activity log
        </Link>
      </div>
    </form>
  );
}

export function AutomationCard() {
  const automation = useQuery({
    queryKey: ["settings", "automation"],
    queryFn: api.automation,
    refetchInterval: 15_000,
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Automatic rules</CardTitle>
        <CardDescription>
          Rules that are switched on run by themselves when Radarr or Sonarr report a new or
          upgraded film or episode.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {automation.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : automation.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {automation.error.message}
          </p>
        ) : (
          <AutomationForm
            key={`${automation.data.settle_seconds}-${automation.data.watch_folders}-${automation.data.rescan_minutes}`}
            initial={automation.data}
          />
        )}
      </CardContent>
    </Card>
  );
}
