/**
 * Subscription status as users see it. The DB column also carries internal
 * checkout bookkeeping (e.g. `pending:<PLAN>|<session>`), which must never
 * reach the browser.
 */
export type SubscriptionStatus =
  | "active"
  | "pending"
  | "cancelled"
  | "payment_issue"
  | "expired";

const LABELS: Record<Exclude<SubscriptionStatus, "active">, string> = {
  pending: "Upgrade pending",
  cancelled: "Cancelled",
  payment_issue: "Payment issue",
  expired: "Expired",
};

export function publicSubscriptionStatus(
  raw: string | null | undefined,
): SubscriptionStatus | null {
  const s = (raw ?? "").trim().toLowerCase();
  if (!s) return null;
  if (s === "active" || s === "renewed") return "active";
  if (s.startsWith("pending")) return "pending";
  if (s === "cancelled" || s === "canceled") return "cancelled";
  if (s === "expired") return "expired";
  if (["on_hold", "past_due", "failed", "paused"].includes(s)) {
    return "payment_issue";
  }
  return null;
}

/** Short label for non-active states; null when nothing needs saying. */
export function subscriptionStatusLabel(
  status: string | null | undefined,
): string | null {
  const s = publicSubscriptionStatus(status);
  return s && s !== "active" ? LABELS[s] : null;
}
