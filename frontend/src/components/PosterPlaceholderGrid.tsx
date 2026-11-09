/** A faded grid of empty poster shapes, shown behind "coming soon" messages. */
export function PosterPlaceholderGrid({ count = 12 }: { count?: number }) {
  return (
    <div
      aria-hidden
      className="grid grid-cols-2 gap-3 opacity-60 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-8"
    >
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className={i >= 4 ? "hidden flex-col gap-2 md:flex" : "flex flex-col gap-2"}>
          <div className="aspect-[2/3] rounded-lg border bg-gradient-to-b from-muted to-card" />
          <div className="h-3 w-3/4 rounded bg-muted" />
          <div className="h-2.5 w-1/3 rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}
