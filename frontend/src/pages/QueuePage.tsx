import { ListOrdered } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

export function QueuePage() {
  return (
    <>
      <PageHeader title="Queue" description="Jobs that are waiting, running or finished." />
      <EmptyState icon={ListOrdered} title="Nothing in the queue">
        <p>
          When you ask Tailarr to change a file, the job shows up here with its progress. Your
          original files are never changed without asking you first.
        </p>
      </EmptyState>
    </>
  );
}
