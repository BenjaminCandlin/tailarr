import { Badge } from "@/components/ui/badge";
import type { MediaSummary } from "@/lib/api";
import { summaryBadges } from "@/lib/hdr";
import { cn } from "@/lib/utils";

/**
 * DV / HDR10+ / HDR10 / HLG / 4K badges for a file.
 * `overlay` gives them a solid background so they stay readable on top of posters.
 */
export function MediaBadges({
  media,
  overlay = false,
  className,
}: {
  media: MediaSummary;
  overlay?: boolean;
  className?: string;
}) {
  const badges = summaryBadges(media);
  if (badges.length === 0) return null;
  return (
    <span className={cn("flex flex-wrap gap-1", className)}>
      {badges.map((badge) => (
        <Badge
          key={badge.label}
          tone={badge.tone}
          title={badge.title}
          className={cn(
            overlay && "shadow-sm ring-1 ring-black/10",
            overlay && badge.tone === "neutral" && "bg-card/95 text-foreground",
            overlay && badge.tone === "accent" && "bg-primary text-primary-foreground",
          )}
        >
          {badge.title === badge.label ? (
            badge.label
          ) : (
            <>
              <span aria-hidden>{badge.label}</span>
              <span className="sr-only">{badge.title}</span>
            </>
          )}
        </Badge>
      ))}
    </span>
  );
}
