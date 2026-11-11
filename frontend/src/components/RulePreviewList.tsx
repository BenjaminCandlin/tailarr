import { AlertTriangle, MinusCircle } from "lucide-react";
import { Link } from "react-router";

import type { RulePreview } from "@/lib/api";
import { formatSize, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

function itemLink(kind: string, id: number): string {
  return kind === "film" ? `/films/${id}` : `/tv/episodes/${id}`;
}

/** What a rule would do to the library right now, file by file. Nothing is changed. */
export function RulePreviewList({ preview }: { preview: RulePreview }) {
  const running = preview.items.filter((i) => i.will_run);
  const skipped = preview.items.filter((i) => !i.will_run);
  return (
    <div className="flex flex-col gap-3 text-sm" data-testid="rule-preview">
      <p data-testid="rule-preview-counts">
        <span className="font-medium">{plural(preview.will_run, "file")}</span> would{" "}
        {preview.changes_originals ? "be changed" : "get a copy"}
        {preview.skipped > 0 && `, ${preview.skipped} matched but would be skipped`}.{" "}
        <span className="text-muted-foreground">
          {plural(preview.not_matching, "file")} didn't match.
          {preview.not_read > 0 &&
            ` ${plural(preview.not_read, "file")} not read yet (they'll be checked once Tailarr has read them).`}
        </span>
      </p>
      {preview.changes_originals && running.length > 0 && (
        <div className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive-soft p-3 text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>This rule changes original files (only their track settings).</p>
        </div>
      )}
      {running.length > 0 && (
        <ul className="flex flex-col gap-1.5" aria-label="Files the rule would change">
          {running.map((item) => (
            <li key={`${item.kind}-${item.id}`} className="rounded-lg border px-3 py-2">
              <Link
                to={itemLink(item.kind, item.id)}
                className="font-medium text-primary underline-offset-4 [overflow-wrap:anywhere] hover:underline"
              >
                {item.label}
              </Link>
              {item.new_file && (
                <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
                  New file: {item.new_file}
                </p>
              )}
              <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                {item.lines.map((line) => (
                  <li key={line} className="[overflow-wrap:anywhere]">
                    {line}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {skipped.length > 0 && (
        <details className="rounded-lg border px-3 py-2" open={running.length === 0}>
          <summary className="min-h-9 cursor-pointer py-1 font-medium">
            Matched but skipped ({skipped.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-2" aria-label="Skipped files">
            {skipped.map((item) => (
              <li key={`${item.kind}-${item.id}`} className="flex gap-2">
                <MinusCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="[overflow-wrap:anywhere]">
                  <span className="font-medium">{item.label}</span>
                  <span className="text-muted-foreground"> – {item.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {preview.space.map((space) => (
        <p key={space.label} className={cn(!space.enough && "font-medium text-destructive")}>
          Space needed on {space.label}: {formatSize(space.needed)} ({formatSize(space.free)} free)
          {!space.enough && ". Not enough free space."}
        </p>
      ))}
    </div>
  );
}
