"use client";

import SupportTicketListPage from "@/components/support/SupportTicketListPage";
import { SELLER_SUPPORT_PORTAL } from "@/lib/support";

export default function SellerSupportTicketsRoute() {
  return <SupportTicketListPage portal={SELLER_SUPPORT_PORTAL} />;
}
