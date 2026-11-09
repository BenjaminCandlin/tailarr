import { ListChecks } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

export function RulesPage() {
  return (
    <>
      <PageHeader
        title="Rules"
        description="Changes Tailarr makes by itself when a new film or episode arrives."
      />
      <EmptyState icon={ListChecks} title="No rules yet">
        <p>
          Later you'll be able to create rules like{" "}
          <em>"If a new film has Dolby Vision, make an HDR10 copy"</em>. You can preview what a rule
          would do before switching it on.
        </p>
      </EmptyState>
    </>
  );
}
