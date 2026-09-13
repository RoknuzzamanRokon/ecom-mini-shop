import { redirect } from "next/navigation";

export default async function AccountOrderDetailPage({
  params,
}: {
  params: Promise<{ orderNumber: string }>;
}) {
  const { orderNumber } = await params;
  redirect(`/profile/orders/${orderNumber}`);
}
