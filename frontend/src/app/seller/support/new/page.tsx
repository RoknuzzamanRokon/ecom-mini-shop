"use client";

import SupportNewTicketPage from "@/components/support/SupportNewTicketPage";
import { SELLER_SUPPORT_PORTAL } from "@/lib/support";

export default function SellerNewSupportTicketRoute() {
  return <SupportNewTicketPage portal={SELLER_SUPPORT_PORTAL} />;
}
