import { CircleAlert, CircleCheck, CircleMinus } from "lucide-react";

export type Status = "ok" | "problem" | "optional";

export function StatusIcon({ status }: { status: Status }) {
  if (status === "ok")
    return <CircleCheck className="size-5 shrink-0 text-success" aria-label="Working" />;
  if (status === "optional")
    return (
      <CircleMinus
        className="size-5 shrink-0 text-muted-foreground"
        aria-label="Not set up (optional)"
      />
    );
  return <CircleAlert className="size-5 shrink-0 text-destructive" aria-label="Problem" />;
}
