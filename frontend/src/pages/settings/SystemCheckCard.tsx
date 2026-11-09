import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { StatusIcon, type Status } from "@/components/StatusIcon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type FolderStatus, type Health } from "@/lib/api";

function folderNote(folder: FolderStatus): string | null {
  if (!folder.exists) {
    return folder.required
      ? "This folder can't be found. Check the folder settings here and the container's /data setting in Unraid."
      : "Not set up. That's fine.";
  }
  if (!folder.writable) return "Tailarr can't save files here. Check the folder's permissions.";
  return null;
}

function permissionsNote(health: Health): string | null {
  const { uid, gid, umask } = health.running_as;
  if (uid === 99 && gid === 100 && umask === "002") return null;
  return "Unraid normally uses user 99, group 100 and umask 002 (PUID, PGID and UMASK in the container settings).";
}

function Row({
  status,
  title,
  detail,
  note,
}: {
  status: Status;
  title: string;
  detail: string;
  note?: string | null;
}) {
  return (
    <li className="flex items-start gap-3 py-3">
      <StatusIcon status={status} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs [overflow-wrap:anywhere] text-muted-foreground">{detail}</p>
        {note && <p className="mt-1 text-xs text-foreground">{note}</p>}
      </div>
    </li>
  );
}

function SectionHeading({ id, children }: { id: string; children: string }) {
  return (
    <h3 id={id} className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

export function SystemCheckCard() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const data = health.data;
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle>System check</CardTitle>
          <CardDescription>The tools and folders Tailarr needs.</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <Badge tone={data.ok ? "success" : "danger"}>
              {data.ok ? "All good" : "Needs attention"}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => void health.refetch()}
            aria-label="Check again"
            title="Check again"
          >
            <RefreshCw className={health.isFetching ? "animate-spin" : ""} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {health.isPending && <Skeleton className="h-64 w-full" />}
        {health.isError && <p className="text-sm text-destructive">{health.error.message}</p>}
        {data && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section aria-labelledby="tools-heading">
              <SectionHeading id="tools-heading">Tools</SectionHeading>
              <ul className="divide-y">
                {data.tools.map((tool) => (
                  <Row
                    key={tool.name}
                    status={tool.ok ? "ok" : "problem"}
                    title={tool.label}
                    detail={`${tool.purpose}${tool.version ? ` · version ${tool.version}` : ""}`}
                    note={
                      tool.ok
                        ? null
                        : "Not installed. Make sure you're using the official Tailarr image."
                    }
                  />
                ))}
              </ul>
            </section>
            <section aria-labelledby="folders-heading">
              <SectionHeading id="folders-heading">Folders</SectionHeading>
              <ul className="divide-y">
                {data.folders.map((folder) => (
                  <Row
                    key={folder.key}
                    status={folder.ok ? (folder.exists ? "ok" : "optional") : "problem"}
                    title={folder.label}
                    detail={`${folder.path} · ${folder.purpose}`}
                    note={folderNote(folder)}
                  />
                ))}
                <Row
                  status={permissionsNote(data) ? "problem" : "ok"}
                  title="File permissions"
                  detail={`New files are saved as user ${data.running_as.uid}, group ${data.running_as.gid}, umask ${data.running_as.umask}`}
                  note={permissionsNote(data)}
                />
              </ul>
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
