import { NextResponse } from "next/server";

import { unauthorized } from "@/lib/api/schemas";
import { requireCurrentUser } from "@/lib/auth/session";
import {
  activatePlanForUser,
  syncApiKeysToAccountPlan,
} from "@/lib/billing/sync";
import {
  planFromDodoProductId,
  type PlanId,
} from "@/lib/billing/plans";
import { publicSubscriptionStatus } from "@/lib/billing/status";
import { db } from "@/lib/db";

function dodoBase(): string {
  const env = process.env.DODO_PAYMENTS_ENVIRONMENT?.trim() || "test_mode";
  return env === "live_mode"
    ? "https://live.dodopayments.com"
    : "https://test.dodopayments.com";
}

function authHeaders(apiKey: string) {
  return { Authorization: `Bearer ${apiKey}` };
}

async function dodoJson(
  path: string,
  apiKey: string
): Promise<Record<string, unknown>> {
  const res = await fetch(`${dodoBase()}${path}`, {
    headers: authHeaders(apiKey),
    cache: "no-store",
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    console.warn("[billing/reconcile] dodo", path, res.status, data);
    return {};
  }
  return data;
}

function asList(data: Record<string, unknown>): Record<string, unknown>[] {
  if (Array.isArray(data.items)) return data.items as Record<string, unknown>[];
  if (Array.isArray(data.data)) return data.data as Record<string, unknown>[];
  return [];
}

async function findCustomerIdByEmail(
  email: string,
  apiKey: string
): Promise<string | null> {
  const data = await dodoJson(
    `/customers?email=${encodeURIComponent(email)}`,
    apiKey
  );
  const items = asList(data);
  const match = items.find(
    (c) =>
      typeof c.email === "string" &&
      c.email.toLowerCase() === email.toLowerCase()
  );
  const id =
    (typeof match?.customer_id === "string" && match.customer_id) ||
    (typeof match?.id === "string" && match.id) ||
    null;
  return id;
}

function pickActiveSubscription(items: Record<string, unknown>[]) {
  return items.find((s) => {
    const st = String(s.status ?? "").toLowerCase();
    return (
      st === "active" ||
      st === "trialing" ||
      st === "succeeded" ||
      st === "paid"
    );
  });
}

function planFromSub(
  sub: Record<string, unknown>,
  pending: PlanId | null
): PlanId | null {
  const productId =
    (typeof sub.product_id === "string" && sub.product_id) ||
    undefined;
  return (productId && planFromDodoProductId(productId)) || pending || null;
}

/**
 * After checkout return: sync keys + pull active subscription from Dodo.
 * Does not rely on webhooks (localhost / misconfigured dashboard still works).
 */
export async function POST() {
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
      subscriptionStatus: true,
      dodoCustomerId: true,
      renderCredits: true,
      billingPeriod: true,
      email: true,
    },
  });

  if (!row) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  await syncApiKeysToAccountPlan(user.id, row.plan);

  if (row.plan === "HOBBY" || row.plan === "PRO" || row.plan === "OWNER") {
    return NextResponse.json({
      ok: true,
      plan: row.plan,
      renderCredits: row.renderCredits,
      subscriptionStatus: publicSubscriptionStatus(row.subscriptionStatus),
      billingPeriod: row.billingPeriod,
      synced: true,
    });
  }

  const pendingRaw = row.subscriptionStatus?.startsWith("pending:")
    ? row.subscriptionStatus.slice("pending:".length)
    : null;
  // pending may be "HOBBY" or "HOBBY|cs_xxx"
  const pendingParts = pendingRaw?.split("|") ?? [];
  const pending = (pendingParts[0]?.toUpperCase() as PlanId | undefined) ?? null;
  const sessionId = pendingParts[1] || null;

  const apiKey = process.env.DODO_PAYMENTS_API_KEY?.trim();
  if (!apiKey) {
    return NextResponse.json({
      ok: true,
      plan: row.plan,
      renderCredits: row.renderCredits,
      subscriptionStatus: publicSubscriptionStatus(row.subscriptionStatus),
      pending,
      synced: false,
      reason: "missing_dodo_key",
    });
  }

  let customerId = row.dodoCustomerId;

  // 1) Resolve customer via stored id, checkout session, or email lookup
  if (!customerId && sessionId) {
    const session = await dodoJson(
      `/checkouts/${encodeURIComponent(sessionId)}`,
      apiKey
    );
    const cust =
      session.customer && typeof session.customer === "object"
        ? (session.customer as Record<string, unknown>)
        : {};
    customerId =
      (typeof session.customer_id === "string" && session.customer_id) ||
      (typeof cust.customer_id === "string" && cust.customer_id) ||
      null;
  }

  if (!customerId && row.email) {
    customerId = await findCustomerIdByEmail(row.email, apiKey);
  }

  if (customerId && customerId !== row.dodoCustomerId) {
    await db.user.update({
      where: { id: user.id },
      data: { dodoCustomerId: customerId },
    });
  }

  if (!customerId) {
    return NextResponse.json({
      ok: true,
      plan: row.plan,
      renderCredits: row.renderCredits,
      subscriptionStatus: publicSubscriptionStatus(row.subscriptionStatus),
      pending,
      synced: false,
      reason: "missing_customer",
      hint: "Complete checkout, then click Refresh plan. Ensure webhook events are enabled in Dodo.",
    });
  }

  // 2) Active subscriptions for this customer
  const subData = await dodoJson(
    `/subscriptions?customer_id=${encodeURIComponent(customerId)}`,
    apiKey
  );
  const active = pickActiveSubscription(asList(subData));

  if (active) {
    const plan = planFromSub(active, pending);
    if (plan && plan !== "FREE") {
      await activatePlanForUser({
        userId: user.id,
        plan,
        dodoCustomerId: customerId,
        dodoSubscriptionId:
          (typeof active.subscription_id === "string" &&
            active.subscription_id) ||
          (typeof active.id === "string" && active.id) ||
          null,
        status: "active",
      });
      const refreshed = await db.user.findUnique({
        where: { id: user.id },
        select: {
          plan: true,
          renderCredits: true,
          subscriptionStatus: true,
          billingPeriod: true,
        },
      });
      return NextResponse.json({
        ok: true,
        plan: refreshed?.plan ?? plan,
        renderCredits: refreshed?.renderCredits ?? 0,
        subscriptionStatus: publicSubscriptionStatus(refreshed?.subscriptionStatus ?? "active"),
        billingPeriod: refreshed?.billingPeriod ?? null,
        synced: true,
        source: "dodo_subscriptions",
      });
    }
  }

  // 3) Last resort: if we have a pending plan from our checkout stamp and
  //    the customer exists in Dodo after a successful pay, activate pending.
  //    Only when subscription list is empty but customer was just created —
  //    still require at least one payment-looking signal via payments list.
  const payData = await dodoJson(
    `/payments?customer_id=${encodeURIComponent(customerId)}`,
    apiKey
  );
  const paid = asList(payData).find((p) => {
    const st = String(p.status ?? "").toLowerCase();
    return st === "succeeded" || st === "paid" || st === "complete";
  });

  if (paid && pending && (pending === "HOBBY" || pending === "PRO")) {
    const productId =
      (typeof paid.product_id === "string" && paid.product_id) ||
      undefined;
    const plan =
      (productId && planFromDodoProductId(productId)) || pending;
    if (plan !== "FREE") {
      await activatePlanForUser({
        userId: user.id,
        plan,
        dodoCustomerId: customerId,
        status: "active",
      });
      const refreshed = await db.user.findUnique({
        where: { id: user.id },
        select: {
          plan: true,
          renderCredits: true,
          subscriptionStatus: true,
          billingPeriod: true,
        },
      });
      return NextResponse.json({
        ok: true,
        plan: refreshed?.plan ?? plan,
        renderCredits: refreshed?.renderCredits ?? 0,
        subscriptionStatus: publicSubscriptionStatus(refreshed?.subscriptionStatus ?? "active"),
        billingPeriod: refreshed?.billingPeriod ?? null,
        synced: true,
        source: "dodo_payments",
      });
    }
  }

  return NextResponse.json({
    ok: true,
    plan: row.plan,
    renderCredits: row.renderCredits,
    subscriptionStatus: publicSubscriptionStatus(row.subscriptionStatus),
    billingPeriod: row.billingPeriod,
    pending,
    synced: false,
    reason: "no_active_subscription_yet",
    hint: "If you just paid, wait ~10s and click Refresh plan. Also enable subscription.active + payment.succeeded in Dodo → Developers → Webhooks.",
  });
}
