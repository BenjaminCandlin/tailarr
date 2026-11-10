import { Film as FilmIcon } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A film or show poster. Without artwork (or if the picture can't be loaded)
 * it shows a calm placeholder with the title, so every card still looks tidy.
 */
export function Poster({
  src,
  title,
  className,
  compact = false,
}: {
  src: string | null;
  title: string;
  className?: string;
  /** Small sizes (list view): icon only, no title text. */
  compact?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const showImage = src && !failed;
  return (
    <div
      className={cn(
        "relative aspect-[2/3] overflow-hidden rounded-lg border bg-gradient-to-b from-muted to-card",
        className,
      )}
    >
      {showImage ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="size-full object-cover"
        />
      ) : (
        <div
          className={cn(
            "flex size-full flex-col items-center justify-center text-center text-muted-foreground",
            compact ? "p-1" : "gap-3 p-3",
          )}
          data-testid="poster-placeholder"
        >
          <FilmIcon className={compact ? "size-4" : "size-8 opacity-70"} aria-hidden />
          {!compact && (
            <span className="line-clamp-4 w-full text-sm font-medium [overflow-wrap:anywhere] text-foreground/80">
              {title}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
