import { useQuery } from "@tanstack/react-query";
import { Tv } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { PosterPlaceholderGrid } from "@/components/PosterPlaceholderGrid";
import { api } from "@/lib/api";

export function TvPage() {
  const settings = useQuery({ queryKey: ["settings", "library"], queryFn: api.librarySettings });
  return (
    <>
      <PageHeader title="TV" description="Shows, seasons and episodes in your TV folder." />
      <div className="relative">
        <PosterPlaceholderGrid />
        <div className="absolute inset-0 flex items-start justify-center bg-gradient-to-b from-background/40 via-background/80 to-background pt-6 md:pt-16 [&>*]:w-full [&>*]:max-w-xl">
          <EmptyState icon={Tv} title="Your TV shows will appear here">
            <p>
              TV browsing comes after the film features. Tailarr will list the shows in{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 break-all text-foreground">
                {settings.data?.tv_dir ?? "your TV folder"}
              </code>
              , by show, season and episode.
            </p>
          </EmptyState>
        </div>
      </div>
    </>
  );
}
