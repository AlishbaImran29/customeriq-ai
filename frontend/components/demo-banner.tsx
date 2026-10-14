import { Info } from "lucide-react";

export function DemoBanner() {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <p>
        Showing realistic <strong>sample data</strong>. Backend, database, and AI
        integrations are not connected.
      </p>
    </div>
  );
}
