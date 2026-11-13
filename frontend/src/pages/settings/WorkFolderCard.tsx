import { useQuery } from "@tanstack/react-query";

import { StatusIcon } from "@/components/StatusIcon";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

/** Whether the optional /work folder is set up, why you'd want one, and how to add it. */
export function WorkFolderCard() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const work = health.data?.folders.find((f) => f.key === "work");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Work folder</CardTitle>
        <CardDescription>
          Optional. Makes copies without Dolby Vision quicker; everything works without it.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {health.isPending ? (
          <Skeleton className="h-10 w-full" />
        ) : work ? (
          <div className="flex items-start gap-3" data-testid="work-folder-status">
            <StatusIcon status={work.exists ? (work.ok ? "ok" : "problem") : "optional"} />
            <p>
              {work.exists && work.writable
                ? `Set up: Tailarr uses ${work.path} for its working files.`
                : work.exists
                  ? `${work.path} is there, but Tailarr can't write to it. Check the folder's permissions (it should belong to user 99, group 100 on Unraid).`
                  : "Not set up: working files go next to the film (hidden) and are removed afterwards."}
            </p>
          </div>
        ) : null}
        <div>
          <p className="font-medium">Why have one?</p>
          <p className="text-muted-foreground">
            While making a copy without Dolby Vision, Tailarr writes two temporary files about the
            size of the film. On Unraid's array every write also updates parity, which is slow. A
            work folder on a fast SSD (such as your cache pool) keeps those temporary files off the
            array: only the finished copy is written there. Tailarr empties it after every job.
          </p>
        </div>
        <div>
          <p className="font-medium">How to add one</p>
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>
              In Unraid, go to <span className="text-foreground">Docker</span>, click the Tailarr
              icon and choose <span className="text-foreground">Edit</span>.
            </li>
            <li>
              If you see a <span className="text-foreground">Work folder (optional)</span> field,
              fill it in. Otherwise click{" "}
              <span className="text-foreground">Add another Path, Port, Variable…</span>, choose{" "}
              <span className="text-foreground">Path</span>, and set{" "}
              <span className="text-foreground">Container Path</span> to{" "}
              <span className="font-mono text-foreground">/work</span>.
            </li>
            <li>
              Set the host path to a folder on your SSD, for example{" "}
              <span className="font-mono text-foreground">/mnt/cache/tailarr-work</span> (Unraid
              creates it). It needs room for about twice your biggest film.
            </li>
            <li>
              Click <span className="text-foreground">Apply</span>. When Tailarr restarts, this box
              shows “Set up”.
            </li>
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
