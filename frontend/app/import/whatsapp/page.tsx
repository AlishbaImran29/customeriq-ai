import { MessagesSquare } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/states";
import { WhatsAppImport } from "@/components/whatsapp-import";
import { WHATSAPP_IMPORT_AVAILABLE } from "@/lib/api/whatsapp";

export default function WhatsAppImportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Import WhatsApp Chat"
        description="Turn orders agreed in a WhatsApp chat into orders in CustomerIQ AI. You review every suggestion; nothing is saved until you accept it."
      />
      {WHATSAPP_IMPORT_AVAILABLE ? (
        <WhatsAppImport />
      ) : (
        <EmptyState
          icon={MessagesSquare}
          title="Importing a chat needs the backend"
          description="Demo mode has no database to save to. Connect the backend (NEXT_PUBLIC_API_BASE_URL) to import orders from WhatsApp."
        />
      )}
    </div>
  );
}
