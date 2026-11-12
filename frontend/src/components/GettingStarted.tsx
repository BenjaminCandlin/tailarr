import { useQuery } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const KEY = "tailarr-welcome-dismissed";

function dismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** A few first steps, shown until dismissed or until Radarr/Sonarr/Plex are connected. */
export function GettingStarted() {
  const [hidden, setHidden] = useState(dismissed);
  const connections = useQuery({ queryKey: ["settings", "connections"], queryFn: api.connections });
  const data = connections.data;
  const connected = data && [data.radarr, data.sonarr, data.plex].some((s) => s.url && s.has_key);
  if (hidden || !data || connected) return null;
  return (
    <section
      aria-labelledby="getting-started"
      className="relative mb-6 rounded-xl border border-primary/40 bg-accent/30 p-4 text-sm"
    >
      <button
        type="button"
        onClick={() => {
          setHidden(true);
          try {
            localStorage.setItem(KEY, "1");
          } catch {
            // Shown again next time; harmless.
          }
        }}
        className="absolute top-2 right-2 inline-flex size-11 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-muted md:size-9"
        aria-label="Hide these tips"
      >
        <X className="size-4" aria-hidden />
      </button>
      <h2 id="getting-started" className="flex items-center gap-2 pr-10 font-medium">
        <Sparkles className="size-4 text-primary" aria-hidden />
        Getting started
      </h2>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
        <li>
          Check the{" "}
          <Link to="/settings" className="text-primary underline underline-offset-4">
            System check
          </Link>{" "}
          in Settings shows green ticks for every tool and folder.
        </li>
        <li>
          Connect{" "}
          <Link to="/settings" className="text-primary underline underline-offset-4">
            Radarr, Sonarr and Plex
          </Link>{" "}
          (optional): proper posters and titles, and your copies kept tidy when files are upgraded.
        </li>
        <li>
          Open any film to see its tracks and HDR, and try a{" "}
          <Link to="/rules" className="text-primary underline underline-offset-4">
            rule
          </Link>
          : you always see a preview first, and originals are never changed without asking.
        </li>
      </ol>
      <div className="mt-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setHidden(true);
            try {
              localStorage.setItem(KEY, "1");
            } catch {
              // Shown again next time; harmless.
            }
          }}
        >
          Got it
        </Button>
      </div>
    </section>
  );
}
