"use client";

import SupportNewTicketPage from "@/components/support/SupportNewTicketPage";
import { CUSTOMER_SUPPORT_PORTAL } from "@/lib/support";

export default function NewSupportTicketRoute() {
  return <SupportNewTicketPage portal={CUSTOMER_SUPPORT_PORTAL} />;
}
