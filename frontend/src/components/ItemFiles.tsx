import { FileVideo, Link2, Replace } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { FileContents } from "@/components/FileContents";
import { MediaBadges } from "@/components/MediaBadges";
import { ReplaceOriginalDialog } from "@/components/ReplaceOriginalDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type FilmFile, type ItemRef } from "@/lib/api";
import { formatDate, formatSize } from "@/lib/format";

function FileRow({
  file,
  item,
  onReplaced,
}: {
  file: FilmFile;
  item: ItemRef;
  onReplaced: () => void;
}) {
  const [replacing, setReplacing] = useState(false);
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <FileVideo className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium [overflow-wrap:anywhere]">{file.name}</p>
          <p className="text-xs text-muted-foreground">
            {formatSize(file.size)} · Changed {formatDate(file.modified_at)}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 pl-8">
        {file.is_main && <Badge tone="accent">Main file</Badge>}
        <MediaBadges media={file.media} />
        {file.is_copy && <Badge>Copy made by Tailarr</Badge>}
        {!file.is_mkv && <Badge tone="warning">Not an MKV file</Badge>}
        {file.hardlinked && (
          <Badge tone="warning">
            <Link2 className="size-3" aria-hidden />
            Also in your downloads
          </Badge>
        )}
      </div>
      {file.hardlinked && (
        <p className="pl-8 text-xs text-muted-foreground">
          This file is hardlinked: the same file is also in another folder, usually because it's
          still seeding in your download client. Making a new copy is always safe. Changing this
          file directly would also change the seeding copy.
        </p>
      )}
      {!file.is_mkv && (
        <p className="pl-8 text-xs text-muted-foreground">
          Tailarr can only change MKV files, so this one is shown for information only.
        </p>
      )}
      {file.copy_of && (
        <p className="pl-8 text-xs text-muted-foreground [overflow-wrap:anywhere]">
          Made from {file.copy_of}
        </p>
      )}
      {file.can_replace_original && (
        <div className="pl-8">
          <Button variant="secondary" onClick={() => setReplacing(true)}>
            <Replace aria-hidden />
            Replace the original with this copy…
          </Button>
          {replacing && (
            <ReplaceOriginalDialog
              item={item}
              copyFile={file.name}
              open
              onOpenChange={setReplacing}
              onReplaced={onReplaced}
            />
          )}
        </div>
      )}
    </li>
  );
}

function fileLabel(file: FilmFile): string {
  if (file.is_main) return `Main file: ${file.name}`;
  if (file.is_copy) return `Copy: ${file.name}`;
  return file.name;
}

/**
 * "What's inside" (tracks, HDR and every action) and the list of files, for one film or
 * one episode. The chosen file is remembered in the address (?file=…).
 */
export function ItemFiles({
  item,
  files,
  mainFile,
  folderWord,
}: {
  item: ItemRef;
  files: FilmFile[];
  mainFile: string | null;
  /** "film" or "episode", for the help text. */
  folderWord: string;
}) {
  const [params, setParams] = useSearchParams();
  const wanted = params.get("file");
  const selected = files.find((f) => f.name === wanted) ?? files.find((f) => f.is_main) ?? files[0];

  function choose(name: string) {
    const next = new URLSearchParams(params);
    if (name === mainFile) next.delete("file");
    else next.set("file", name);
    setParams(next, { replace: true });
  }

  return (
    <div className="flex flex-col gap-6">
      {selected && (
        <Card>
          <CardHeader>
            <CardTitle>What's inside</CardTitle>
            <CardDescription>
              The picture, sound and subtitle tracks, read with MKVToolNix and MediaInfo.
            </CardDescription>
            {files.length > 1 && (
              <div className="mt-2 flex flex-col gap-1.5">
                <label htmlFor="file-choice" className="text-sm font-medium">
                  File
                </label>
                <select
                  id="file-choice"
                  value={selected.name}
                  onChange={(e) => choose(e.target.value)}
                  className="h-11 w-full max-w-full min-w-0 cursor-pointer truncate rounded-lg border border-input bg-background px-3 text-base md:h-10 md:text-sm"
                >
                  {files.map((file) => (
                    <option key={file.name} value={file.name}>
                      {fileLabel(file)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </CardHeader>
          <CardContent>
            <FileContents
              key={selected.name}
              queryKey={[item.kind, String(item.id), "media", selected.name]}
              load={(refresh) => api.media(item, selected.name, refresh)}
              edit={selected.is_mkv ? { item, file: selected.name, onOpenFile: choose } : undefined}
            />
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Files</CardTitle>
          <CardDescription>The video files for this {folderWord}.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {files.map((file) => (
              <FileRow
                key={file.name}
                file={file}
                item={item}
                onReplaced={() => choose(mainFile ?? "")}
              />
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
