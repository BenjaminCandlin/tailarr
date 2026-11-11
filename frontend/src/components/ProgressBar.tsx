import { cn } from "@/lib/utils";

/**
 * A progress bar. With no percentage (null) it shows a moving band, so the owner
 * can see something is happening.
 */
export function ProgressBar({
  value,
  label,
  className,
}: {
  value: number | null;
  label: string;
  className?: string;
}) {
  const known = value !== null;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? Math.round(value) : undefined}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      {known ? (
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500"
          style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
        />
      ) : (
        <div className="h-full w-2/5 rounded-full bg-primary/80 motion-safe:animate-progress-slide" />
      )}
    </div>
  );
}
