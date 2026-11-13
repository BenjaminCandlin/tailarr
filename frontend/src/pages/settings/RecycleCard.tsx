import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { RestoreDialog } from "@/components/RestoreDialog";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RecycledFile, type RecycleSettings } from "@/lib/api";
import { formatDate, formatSize, plural } from "@/lib/format";

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
          : `${plural(initial.file_count, "file")} waiting, using ${formatSize(
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

function RecycledRow({ file, keepDays }: { file: RecycledFile; keepDays: number }) {
  const [open, setOpen] = useState(false);
  return (
    <li
      className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:gap-4"
      data-testid={`recycled-${file.id}`}
    >
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium [overflow-wrap:anywhere]">{file.name}</p>
        <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
          From {file.folder} · {formatSize(file.size)} · moved there {formatDate(file.recycled_at)}{" "}
          ·{" "}
          {file.days_left === 0
            ? "deleted at the next clean-up"
            : `deleted in ${plural(file.days_left, "day")}`}
        </p>
        {!file.available && (
          <p className="text-xs text-warning">
            No longer in the recycle folder (moved or deleted by hand).
          </p>
        )}
      </div>
      {file.available && (
        <>
          <Button
            variant="secondary"
            className="self-start sm:self-auto"
            onClick={() => setOpen(true)}
          >
            <RotateCcw className="size-4" aria-hidden />
            Restore<span className="sr-only"> {file.name}</span>
          </Button>
          <RestoreDialog file={file} keepDays={keepDays} open={open} onOpenChange={setOpen} />
        </>
      )}
    </li>
  );
}

function RecycledList({ keepDays }: { keepDays: number }) {
  const files = useQuery({
    queryKey: ["settings", "recycle", "files"],
    queryFn: api.recycledFiles,
  });
  if (files.isPending) return <Skeleton className="h-16 w-full" />;
  if (files.isError)
    return (
      <p role="alert" className="text-sm text-destructive">
        {files.error.message}
      </p>
    );
  if (files.data.length === 0) return null;
  return (
    <section className="flex flex-col gap-3 border-t pt-4" aria-labelledby="recycled-heading">
      <div>
        <h3 id="recycled-heading" className="text-sm font-medium">
          Waiting in the recycle folders
        </h3>
        <p className="text-xs text-muted-foreground">
          Changed your mind? <span className="font-medium">Restore</span> puts a file back where it
          was. You'll see a summary first.
        </p>
      </div>
      <ul className="divide-y" data-testid="recycled-files">
        {files.data.map((file) => (
          <RecycledRow key={file.id} file={file} keepDays={keepDays} />
        ))}
      </ul>
    </section>
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
          inside the film's folder, in case you change your mind. Old copies tidied away after a
          Radarr or Sonarr upgrade wait there too.
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
          <div className="flex flex-col gap-4">
            <RecycleForm key={settings.data.keep_days} initial={settings.data} />
            <RecycledList keepDays={settings.data.keep_days} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
