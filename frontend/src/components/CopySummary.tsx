import { AlertTriangle, MinusCircle } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import type { RemoveTracksPreview } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";

/** What "Save a copy without the unticked tracks" will do, in plain words. */
export function CopySummary({
  preview,
  overwrite,
  onOverwrite,
}: {
  preview: RemoveTracksPreview;
  overwrite: boolean;
  onOverwrite: (value: boolean) => void;
}) {
  return (
    <>
      <div className="rounded-lg border bg-muted/50 px-3 py-2">
        <p className="text-xs text-muted-foreground">
          {preview.updates_copy ? "Copy that will be updated" : "New file"}
        </p>
        <p className="font-medium [overflow-wrap:anywhere]" data-testid="summary-new-file">
          {preview.new_file}
        </p>
        {!preview.updates_copy && (
          <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
            Made from {preview.file}, in the same folder
          </p>
        )}
      </div>

      <div>
        <p className="mb-2 font-medium">Left out of the copy</p>
        <ul className="flex flex-col gap-1.5" aria-label="Left out of the copy">
          {preview.removed.map((line) => (
            <li key={line} className="flex gap-2 rounded-lg border px-3 py-2">
              <MinusCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
              <span className="[overflow-wrap:anywhere]">{line}</span>
            </li>
          ))}
        </ul>
      </div>

      {preview.settings.length > 0 && (
        <div>
          <p className="mb-2 font-medium">Also changed in the copy</p>
          <ul className="flex flex-col gap-1.5" aria-label="Also changed in the copy">
            {preview.settings.map((item) => (
              <li key={item.label} className="rounded-lg border px-3 py-2">
                <p className="font-medium">{item.label}</p>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {item.changes.map((change) => (
                    <li key={change}>{change}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details>
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          Kept: {plural(preview.kept.length, "track")}, plus chapters, attachments and the exact
          picture
        </summary>
        <ul className="mt-2 list-disc pl-5 text-muted-foreground">
          {preview.kept.map((line) => (
            <li key={line} className="[overflow-wrap:anywhere]">
              {line}
            </li>
          ))}
        </ul>
      </details>

      {preview.warnings.map((warning) => (
        <p
          key={warning}
          className="flex gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          {warning}
        </p>
      ))}

      <p
        className={preview.enough_space ? "text-muted-foreground" : "font-medium text-destructive"}
      >
        {preview.enough_space ? "Disk space: " : "Not enough free space on the disk: "}
        needs up to {formatSize(preview.space_needed)}, {formatSize(preview.free_space)} free.
        {preview.enough_space &&
          " Nothing is re-encoded, so it's quick: about as long as copying the file."}
      </p>

      {preview.exists && !preview.updates_copy && (
        <div className="flex flex-col gap-2 rounded-lg border border-warning/40 bg-warning-soft p-3">
          <p>
            <span className="font-medium">A copy with this name is already there.</span> It was made
            by Tailarr earlier.
          </p>
          <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium">
            <Checkbox
              checked={overwrite}
              onCheckedChange={(checked) => onOverwrite(checked === true)}
            />
            Replace the existing copy
          </label>
        </div>
      )}
    </>
  );
}
