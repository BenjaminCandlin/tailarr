import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RecycleSettings } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";

function RecycleForm({ initial }: { initial: RecycleSettings }) {
  const queryClient = useQueryClient();
  const [days, setDays] = useState(String(initial.keep_days));
  const save = useMutation({
    mutationFn: () => api.saveRecycleSettings(Number(days)),
    onSuccess: (saved) => queryClient.setQueryData(["settings", "recycle"], saved),
  });
  const number = Number(days);
  const valid = Number.isInteger(number) && number >= 1 && number <= 365;
  const changed = number !== initial.keep_days;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (valid) save.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="keep-days" className="text-sm font-medium">
          Keep replaced originals for (days)
        </label>
        <Input
          id="keep-days"
          type="number"
          inputMode="numeric"
          min={1}
          max={365}
          value={days}
          onChange={(e) => setDays(e.target.value)}
          aria-invalid={!valid || save.isError || undefined}
          className="max-w-32"
        />
        <p className="text-xs text-muted-foreground">
          Between 1 and 365 days. After that they're deleted for good. Shortening this also applies
          to files already waiting.
        </p>
      </div>
      <p className="text-sm" data-testid="recycle-contents">
        {initial.file_count === 0
          ? "The recycle folders are empty."
          : `${plural(initial.file_count, "original")} waiting, using ${formatSize(
              initial.total_size,
            )}.`}
      </p>
      {save.isError && (
        <p
          role="alert"
          className="rounded-lg bg-destructive-soft px-3 py-2 text-sm text-destructive"
        >
          {save.error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!changed || !valid || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        {save.isSuccess && !changed && (
          <p role="status" className="text-sm text-success">
            Saved.
          </p>
        )}
      </div>
    </form>
  );
}

export function RecycleCard() {
  const settings = useQuery({ queryKey: ["settings", "recycle"], queryFn: api.recycleSettings });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recycle folder</CardTitle>
        <CardDescription>
          When you replace an original file with a copy, the original isn't deleted straight away.
          It waits in a hidden <span className="font-mono text-xs">.tailarr-recycle</span> folder
          inside the film's folder, in case you change your mind.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : settings.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {settings.error.message}
          </p>
        ) : (
          <RecycleForm key={settings.data.keep_days} initial={settings.data} />
        )}
      </CardContent>
    </Card>
  );
}
