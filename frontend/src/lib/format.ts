/** Turning numbers and dates into friendly text. */

const UNITS = ["bytes", "KB", "MB", "GB", "TB"];

/** 1536 -> "1.5 KB". Uses 1024 steps, like Unraid and Windows show sizes. */
export function formatSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  if (unit === 0) return `${bytes} bytes`;
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${UNITS[unit]}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "just now", "5 minutes ago", "3 hours ago", "2 days ago". */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const steps: [number, string][] = [
    [60, "minute"],
    [3600, "hour"],
    [86400, "day"],
  ];
  let chosen = steps[0];
  for (const step of steps) if (seconds >= step[0]) chosen = step;
  const count = Math.floor(seconds / chosen[0]);
  return `${count} ${chosen[1]}${count === 1 ? "" : "s"} ago`;
}

/** Lower-case without accents, so "arger" finds "Ärger". */
export function fold(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

export function plural(count: number, word: string, many = `${word}s`): string {
  return `${count.toLocaleString()} ${count === 1 ? word : many}`;
}

/** 8040 -> "2 h 14 min"; 2700 -> "45 min"; 3 -> "3 seconds". */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} second${Math.round(seconds) === 1 ? "" : "s"}`;
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${minutes} min`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** A running time: "4 s", "2 min 05 s", "1 h 03 min". */
export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}
