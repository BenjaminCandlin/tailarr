import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { api } from "@/lib/api";

import { AppearanceCard } from "./settings/AppearanceCard";
import { AutomationCard } from "./settings/AutomationCard";
import { ConnectionsCard } from "./settings/ConnectionsCard";
import { LibraryFoldersCard } from "./settings/LibraryFoldersCard";
import { LoginCard } from "./settings/LoginCard";
import { RecycleCard } from "./settings/RecycleCard";
import { SystemCheckCard } from "./settings/SystemCheckCard";

export function SettingsPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  return (
    <>
      <PageHeader
        title="Settings"
        description="Folders, connections, automatic rules, login, appearance, the recycle folder and a check that everything works."
      />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <div className="xl:col-span-2">
          <SystemCheckCard />
        </div>
        <LibraryFoldersCard />
        <AppearanceCard />
        <div className="xl:col-span-2">
          <ConnectionsCard />
        </div>
        <AutomationCard />
        <RecycleCard />
        <LoginCard />
      </div>
      <p className="mt-8 text-center text-xs text-muted-foreground">
        Tailarr {health.data ? `version ${health.data.version}` : ""}
      </p>
    </>
  );
}
