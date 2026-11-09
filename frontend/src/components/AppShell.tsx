import { NavLink, Outlet, useLocation } from "react-router";

import { cn } from "@/lib/utils";

import { Logo } from "./Logo";
import { NAV_ITEMS } from "./nav";

/** Number of jobs running, shown as a badge on Queue. Comes from the job queue (Stage 4). */
function useRunningJobs(): number {
  return 0;
}

function QueueCount({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <span
      className={cn(
        "rounded-full bg-primary px-1.5 text-[11px] leading-5 font-semibold text-primary-foreground",
        className,
      )}
      aria-label={`${count} running`}
    >
      {count}
    </span>
  );
}

function Sidebar() {
  const running = useRunningJobs();
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r bg-sidebar md:flex">
      <div className="flex h-16 items-center gap-3 px-5">
        <Logo />
        <span className="text-lg font-semibold tracking-tight">Tailarr</span>
      </div>
      <nav aria-label="Main" className="flex flex-1 flex-col gap-1 px-3 py-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "group relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    className="absolute inset-y-2 left-0 w-1 rounded-r bg-primary"
                    aria-hidden
                  />
                )}
                <Icon className="size-5" aria-hidden />
                <span className="flex-1">{label}</span>
                {to === "/queue" && <QueueCount count={running} />}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <p className="px-5 py-4 text-xs text-muted-foreground">
        Changes inside MKV files. Never re-encodes.
      </p>
    </aside>
  );
}

function MobileTopBar() {
  const location = useLocation();
  const current = NAV_ITEMS.find((item) => location.pathname.startsWith(item.to));
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-sidebar/95 px-4 backdrop-blur md:hidden">
      <Logo className="size-7" />
      <span className="font-semibold">{current?.label ?? "Tailarr"}</span>
    </header>
  );
}

function BottomTabBar() {
  const running = useRunningJobs();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 border-t bg-sidebar/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      <ul className="grid grid-cols-5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                cn(
                  "relative flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium",
                  isActive ? "text-primary" : "text-muted-foreground",
                )
              }
            >
              <Icon className="size-6" aria-hidden />
              {label}
              {to === "/queue" && (
                <QueueCount count={running} className="absolute top-1.5 left-1/2 ml-2" />
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function AppShell() {
  return (
    <div className="min-h-dvh">
      <Sidebar />
      <MobileTopBar />
      <main className="px-4 pt-5 pb-28 md:ml-60 md:px-8 md:pt-8 md:pb-10">
        <div className="mx-auto max-w-[1600px]">
          <Outlet />
        </div>
      </main>
      <BottomTabBar />
    </div>
  );
}
