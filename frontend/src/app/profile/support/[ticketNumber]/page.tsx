"use client";

import SupportTicketPage from "@/components/support/SupportTicketPage";
import { CUSTOMER_SUPPORT_PORTAL } from "@/lib/support";

export default function SupportTicketRoute() {
  return <SupportTicketPage portal={CUSTOMER_SUPPORT_PORTAL} />;
}
