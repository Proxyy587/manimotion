import { NextResponse } from "next/server";

import { unauthorized } from "@/lib/api/schemas";
import { requireCurrentUser } from "@/lib/auth/session";
import { publicSubscriptionStatus } from "@/lib/billing/status";
import { db } from "@/lib/db";

export async function GET() {
  let user;
  try {
    user = await requireCurrentUser();
  } catch {
    return unauthorized();
  }

  const row = await db.user.findUnique({
    where: { id: user.id },
    select: {
      plan: true,
      renderCredits: true,
      subscriptionStatus: true,
      billingPeriod: true,
    },
  });

  return NextResponse.json({
    plan: row?.plan ?? "FREE",
    renderCredits: row?.renderCredits ?? 0,
    subscriptionStatus: publicSubscriptionStatus(row?.subscriptionStatus),
    billingPeriod: row?.billingPeriod ?? null,
  });
}
