import { useQuery } from "@tanstack/react-query";
import { Clapperboard } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { PosterPlaceholderGrid } from "@/components/PosterPlaceholderGrid";
import { api } from "@/lib/api";

export function FilmsPage() {
  const settings = useQuery({ queryKey: ["settings", "library"], queryFn: api.librarySettings });
  return (
    <>
      <PageHeader title="Films" description="Everything in your Films folder." />
      <div className="relative">
        <PosterPlaceholderGrid />
        <div className="absolute inset-0 flex items-start justify-center bg-gradient-to-b from-background/40 via-background/80 to-background pt-6 md:pt-16 [&>*]:w-full [&>*]:max-w-xl">
          <EmptyState icon={Clapperboard} title="Your films will appear here">
            <p>
              The film library arrives in the next update. Tailarr will list the films in{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 break-all text-foreground">
                {settings.data?.movies_dir ?? "your Films folder"}
              </code>
              , with their posters.
            </p>
          </EmptyState>
        </div>
      </div>
    </>
  );
}
