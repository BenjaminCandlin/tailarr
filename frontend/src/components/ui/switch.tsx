import * as SwitchPrimitive from "@radix-ui/react-switch";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** An on/off switch. The tappable area is 44px tall on phones. */
export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "group relative inline-flex h-11 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full outline-none disabled:cursor-not-allowed disabled:opacity-50 md:h-8",
        className,
      )}
      {...props}
    >
      <span
        aria-hidden
        className="flex h-6 w-11 items-center rounded-full border border-transparent bg-input p-0.5 transition-colors group-focus-visible:ring-2 group-focus-visible:ring-ring group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background group-data-[state=checked]:bg-primary"
      >
        <SwitchPrimitive.Thumb className="block size-5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-5" />
      </span>
    </SwitchPrimitive.Root>
  );
}
