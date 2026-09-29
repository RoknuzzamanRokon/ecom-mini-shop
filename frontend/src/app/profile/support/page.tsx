"use client";

import SupportTicketListPage from "@/components/support/SupportTicketListPage";
import { CUSTOMER_SUPPORT_PORTAL } from "@/lib/support";

export default function SupportTicketsRoute() {
  return <SupportTicketListPage portal={CUSTOMER_SUPPORT_PORTAL} />;
}
