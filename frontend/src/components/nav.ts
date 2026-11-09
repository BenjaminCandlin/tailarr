import { Clapperboard, ListChecks, ListOrdered, Settings, Tv, type LucideIcon } from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; description: string };

export const NAV_ITEMS: NavItem[] = [
  { to: "/films", label: "Films", icon: Clapperboard, description: "Browse your films" },
  { to: "/tv", label: "TV", icon: Tv, description: "Browse your TV shows" },
  {
    to: "/rules",
    label: "Rules",
    icon: ListChecks,
    description: "Automatic changes for new files",
  },
  { to: "/queue", label: "Queue", icon: ListOrdered, description: "Jobs that are running or done" },
  {
    to: "/settings",
    label: "Settings",
    icon: Settings,
    description: "Folders, appearance, system",
  },
];
