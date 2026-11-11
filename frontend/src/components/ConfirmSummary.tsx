import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog";

/**
 * The summary shown before any job: what will happen, which file, and a clear
 * Confirm / Cancel. A dialog on computers, a slide-up sheet on phones.
 */
export function ConfirmSummary({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  onConfirm,
  destructive = false,
  confirmDisabled = false,
  pending = false,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  /** Red confirm button: the action changes an original file. */
  destructive?: boolean;
  confirmDisabled?: boolean;
  pending?: boolean;
  error?: string | null;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description}>
        <DialogBody className="flex flex-col gap-4 text-sm">
          {children}
          {error && (
            <p role="alert" className="rounded-lg bg-destructive-soft px-3 py-2 text-destructive">
              {error}
            </p>
          )}
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">Cancel</Button>
          </DialogClose>
          <Button
            variant={destructive ? "destructive" : "primary"}
            onClick={onConfirm}
            disabled={confirmDisabled || pending}
          >
            {pending ? "Starting…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
