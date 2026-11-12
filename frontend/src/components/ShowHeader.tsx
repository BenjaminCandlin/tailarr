import type { ReactNode } from "react";

import { Poster } from "@/components/Poster";

/** The poster-and-backdrop header of a show or episode page. */
export function ShowHeader({
  title,
  posterUrl,
  backdropUrl,
  children,
}: {
  title: string;
  posterUrl: string | null;
  backdropUrl: string | null;
  children: ReactNode;
}) {
  return (
    <div className="relative mb-6 overflow-hidden rounded-xl border bg-card">
      {backdropUrl && (
        <img
          src={backdropUrl}
          alt=""
          className="absolute inset-0 size-full object-cover opacity-25"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-card via-card/90 to-card/40" />
      <div className="relative flex gap-4 p-4 md:gap-6 md:p-6">
        <Poster
          src={posterUrl && posterUrl.replace("?", "?size=full&")}
          title={title}
          className="w-24 shrink-0 shadow-lg md:w-40"
        />
        <div className="flex min-w-0 flex-col gap-2 py-1">{children}</div>
      </div>
    </div>
  );
}
