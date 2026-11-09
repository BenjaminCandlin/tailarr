import { Compass } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState icon={Compass} title="This page doesn't exist">
      <Button asChild className="mt-4">
        <Link to="/films">Go to Films</Link>
      </Button>
    </EmptyState>
  );
}
