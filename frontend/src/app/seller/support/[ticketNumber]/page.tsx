"use client";

import SupportTicketPage from "@/components/support/SupportTicketPage";
import { SELLER_SUPPORT_PORTAL } from "@/lib/support";

export default function SellerSupportTicketRoute() {
  return <SupportTicketPage portal={SELLER_SUPPORT_PORTAL} />;
}
