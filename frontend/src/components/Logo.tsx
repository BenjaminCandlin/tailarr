export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="14" className="fill-primary" />
      <path
        d="M14 20h36M32 20v28"
        className="stroke-primary-foreground"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <path
        d="M20 44l6-6M44 44l-6-6"
        className="stroke-primary-foreground/60"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}
