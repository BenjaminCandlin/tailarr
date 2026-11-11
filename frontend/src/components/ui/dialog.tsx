import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogClose = DialogPrimitive.Close;

/**
 * A dialog in the middle of the screen on computers, and a sheet that slides up from
 * the bottom on phones (easier to reach with a thumb).
 */
export function DialogContent({
  className,
  children,
  title,
  description,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { title: ReactNode; description?: ReactNode }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] motion-safe:animate-fade-in" />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 flex max-h-[90dvh] flex-col rounded-t-2xl border bg-card text-card-foreground shadow-2xl outline-none",
          "pb-[env(safe-area-inset-bottom)] motion-safe:animate-sheet-up md:motion-safe:animate-fade-in",
          "md:inset-x-auto md:top-1/2 md:bottom-auto md:left-1/2 md:w-full md:max-w-lg md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-2xl md:pb-0",
          className,
        )}
        {...props}
      >
        <div
          className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-muted md:hidden"
          aria-hidden
        />
        <div className="flex items-start gap-3 px-5 pt-4 md:px-6 md:pt-6">
          <div className="min-w-0 flex-1">
            <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-1 text-sm text-muted-foreground">
                {description}
              </DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close
            className="-mt-1 -mr-2 inline-flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground md:size-9"
            aria-label="Close"
          >
            <X className="size-5" aria-hidden />
          </DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** The scrolling middle part of a dialog. */
export function DialogBody({ className, ...props }: ComponentProps<"div">) {
  return (
    <div className={cn("min-h-0 flex-1 overflow-y-auto px-5 py-4 md:px-6", className)} {...props} />
  );
}

/** Buttons at the bottom: stacked on phones (main action first), side by side on computers. */
export function DialogFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-2 border-t px-5 py-4 md:flex-row md:justify-end md:px-6",
        className,
      )}
      {...props}
    />
  );
}
