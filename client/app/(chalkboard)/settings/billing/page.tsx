"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { getPlan, PLANS, PLAN_RANK } from "@/lib/billing/plans";
import { subscriptionStatusLabel } from "@/lib/billing/status";
import { LECTURE_MODELS } from "@/lib/chalkboard-api";
import { readJsonSafe } from "@/lib/http";

// ─── types ────────────────────────────────────────────────────────────────────

type BillingMe = {
  plan: string;
  renderCredits: number;
  subscriptionStatus: string | null;
  billingPeriod: string | null;
};

// ─── helpers ──────────────────────────────────────────────────────────────────

function progressPct(used: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round((used / total) * 100));
}

function barColor(pct: number): string {
  if (pct >= 85) return "bg-red-500";
  if (pct >= 60) return "bg-yellow-400";
  return "bg-emerald-500";
}

function openPortal() {
  const w = window.open("/api/portal", "_blank", "noopener,noreferrer");
  if (!w) toast.error("Allow pop-ups to open the billing portal.");
}

// ─── inner page (needs useSearchParams) ──────────────────────────────────────

function BillingInner() {
  const params = useSearchParams();
  const [me, setMe] = useState<BillingMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const checkoutSuccess = params.get("checkout") === "success";

  const loadMe = useCallback(async (): Promise<BillingMe> => {
    const res = await fetch("/api/billing/me", { credentials: "include" });
    if (!res.ok) throw new Error("Failed to load billing");
    return readJsonSafe<BillingMe>(res);
  }, []);

  // Initial load + optional reconcile polling after checkout
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        if (checkoutSuccess) {
          toast.message("Confirming payment…", {
            description: "Syncing your plan from payment provider.",
          });

          for (let i = 0; i < 8; i++) {
            const res = await fetch("/api/billing/reconcile", {
              method: "POST",
              credentials: "include",
            });
            const data = await readJsonSafe<{
              plan?: string;
              renderCredits?: number;
              subscriptionStatus?: string | null;
              synced?: boolean;
            }>(res);

            if (!cancelled && data.plan) {
              setMe({
                plan: data.plan,
                renderCredits: data.renderCredits ?? 0,
                subscriptionStatus: data.subscriptionStatus ?? null,
                billingPeriod: null,
              });
            }

            if (data.synced && data.plan && data.plan !== "FREE") break;
            await new Promise<void>((r) => setTimeout(r, 1500));
          }

          if (!cancelled) {
            const latest = await loadMe();
            if (!cancelled) setMe(latest);
          }
        } else {
          const data = await loadMe();
          if (!cancelled) setMe(data);
        }
      } catch {
        if (!cancelled) setMe(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [checkoutSuccess, loadMe]);

  // Manual sync (reconcile)
  async function handleSync() {
    setRefreshing(true);
    try {
      const res = await fetch("/api/billing/reconcile", {
        method: "POST",
        credentials: "include",
      });
      const data = await readJsonSafe<BillingMe & { synced?: boolean }>(res);
      setMe({
        plan: data.plan ?? "FREE",
        renderCredits: data.renderCredits ?? 0,
        subscriptionStatus: data.subscriptionStatus ?? null,
        billingPeriod: data.billingPeriod ?? null,
      });
      toast.success(
        data.synced
          ? `Plan synced: ${data.plan}`
          : `Still on ${data.plan ?? "Free"}`,
      );
    } catch {
      toast.error("Could not sync billing");
    } finally {
      setRefreshing(false);
    }
  }

  // ── derived values ──────────────────────────────────────────────────────────

  const plan = getPlan(me?.plan);
  const planId = (me?.plan?.toUpperCase() ?? "FREE") as
    "FREE" | "HOBBY" | "PRO";
  const planRank = PLAN_RANK[planId] ?? 0;
  const isFree = planId === "FREE";
  const statusLabel = subscriptionStatusLabel(me?.subscriptionStatus);

  const quota = isFree ? (plan.dailyRenders ?? 3) : (plan.monthlyRenders ?? 0);
  const used = quota - (me?.renderCredits ?? 0);
  const pct = progressPct(Math.max(0, used), quota);

  const periodLabel = isFree
    ? "Resets daily at midnight UTC"
    : me?.billingPeriod
      ? `Resets ${me.billingPeriod}`
      : "Resets monthly";

  const hasLockedModels = planRank < 2;

  const showBanner =
    checkoutSuccess && !bannerDismissed && !loading && me?.plan !== "FREE";

  // ── skeleton / error states ─────────────────────────────────────────────────

  const card =
    "rounded-[12px] border border-[var(--chip-line)] bg-[var(--surface)] p-5";

  if (loading) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <div className={card}>
          <p className="text-[13px] text-[var(--muted-2)]">Loading billing…</p>
        </div>
      </div>
    );
  }

  if (me === null) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <div className={card}>
          <p className="text-[13px] text-[var(--muted-text)]">
            Could not load billing data.{" "}
            <button
              type="button"
              className="text-foreground underline underline-offset-2 hover:no-underline"
              onClick={() => {
                setLoading(true);
                loadMe()
                  .then((d) => setMe(d))
                  .catch(() => setMe(null))
                  .finally(() => setLoading(false));
              }}
            >
              Retry
            </button>
          </p>
        </div>
      </div>
    );
  }

  // ── main layout ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      <PageHeader />

      {/* ── Current plan card ── */}
      <section className={card}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          {/* Left: plan identity */}
          <div>
            <div className="flex items-center gap-2">
              <span
                className={[
                  "rounded-[6px] px-2 py-0.5 text-[11px] font-semibold tracking-[0.04em]",
                  isFree
                    ? "border border-[var(--chip-line)] bg-[var(--chip)] text-[var(--muted-text)]"
                    : !statusLabel
                      ? "border border-emerald-500/30 bg-emerald-500/8 text-emerald-600 dark:text-emerald-400"
                      : "border border-yellow-500/30 bg-yellow-500/8 text-yellow-600 dark:text-yellow-400",
                ].join(" ")}
              >
                {isFree ? "FREE" : (statusLabel ?? "Active").toUpperCase()}
              </span>
            </div>
            <p className="mt-2 text-[1.5rem] font-bold leading-none tracking-tight text-foreground">
              {plan.name}
            </p>
            <p className="mt-1 text-[13px] text-[var(--muted-text)]">
              {plan.priceUsd === 0
                ? "Free forever"
                : `${plan.priceLabel} / month`}
              {statusLabel ? ` · ${statusLabel}` : ""}
            </p>
          </div>

          {/* Right: renders quota + bar */}
          <div className="min-w-[200px] flex-1">
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-[12px] font-medium text-[var(--ink-soft)]">
                Renders this period
              </p>
              <p className="text-[12px] text-[var(--muted-text)]">
                <span className="font-semibold text-foreground">
                  {me.renderCredits}
                </span>
                {" / "}
                {quota} remaining
              </p>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--chip-line)]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${barColor(pct)}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-1.5 text-[11px] text-[var(--muted-2)]">
              {periodLabel}
            </p>
          </div>
        </div>
      </section>

      {/* ── Two-column grid ── */}
      <div className="grid gap-5 md:grid-cols-2">
        {/* Left: Models */}
        <section className={card}>
          <p className="mm-label">Available models</p>
          <ul className="mt-3 space-y-2">
            {LECTURE_MODELS.map((m) => {
              const modelRank = PLAN_RANK[m.minPlan] ?? 0;
              const unlocked = planRank >= modelRank;
              const requiredPlan = PLANS.find((p) => p.id === m.minPlan);

              return (
                <li key={m.id} className="flex items-center gap-2.5">
                  {unlocked ? (
                    <span className="size-1.5 shrink-0 rounded-full bg-emerald-500" />
                  ) : (
                    <span className="text-[12px] leading-none">🔒</span>
                  )}
                  <span
                    className={[
                      "flex-1 text-[13px]",
                      unlocked ? "text-foreground" : "text-[var(--muted-2)]",
                    ].join(" ")}
                  >
                    {m.label}
                  </span>
                  {unlocked && m.badge && (
                    <span className="rounded-[4px] border border-[var(--chip-line)] bg-[var(--chip)] px-1.5 py-px text-[10px] text-[var(--muted-text)]">
                      {m.badge}
                    </span>
                  )}
                  {!unlocked && requiredPlan && (
                    <span className="rounded-[4px] border border-[var(--chip-line)] px-1.5 py-px text-[10px] text-[var(--muted-2)]">
                      {requiredPlan.name}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>

          {hasLockedModels && (
            <p className="mt-4 text-[12px] text-[var(--muted-text)]">
              <Link
                href="/pricing"
                className="text-foreground underline underline-offset-2 hover:no-underline"
              >
                Upgrade to unlock
              </Link>{" "}
              more models.
            </p>
          )}
        </section>

        {/* Right: Actions */}
        <section className={card}>
          <p className="mm-label">Manage plan</p>

          <div className="mt-3 flex flex-col gap-2">
            {planId === "FREE" && (
              <>
                <Link href="/pricing">
                  <Button type="button" className="w-full justify-start">
                    Upgrade to Hobby — $9/mo
                  </Button>
                </Link>
                <Link href="/pricing">
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full justify-start"
                  >
                    See all plans
                  </Button>
                </Link>
              </>
            )}

            {planId === "HOBBY" && (
              <>
                <Link href="/pricing">
                  <Button type="button" className="w-full justify-start">
                    Upgrade to Pro — $19/mo
                  </Button>
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  className="w-full justify-start"
                  onClick={openPortal}
                >
                  Manage subscription
                </Button>
                <Link href="/pricing">
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full justify-start"
                  >
                    View plans
                  </Button>
                </Link>
              </>
            )}

            {planId === "PRO" && (
              <>
                <Button
                  type="button"
                  className="w-full justify-start"
                  onClick={openPortal}
                >
                  Manage subscription
                </Button>
                <Link href="/pricing">
                  <Button
                    type="button"
                    variant="ghost"
                    className="w-full justify-start"
                  >
                    View plans
                  </Button>
                </Link>
              </>
            )}
          </div>

          <div className="mt-5 border-t border-[var(--chip-line)] pt-4">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={refreshing}
              onClick={handleSync}
              className="text-[12px]"
            >
              {refreshing ? "Syncing…" : "Sync plan"}
            </Button>
            <p className="mt-1 text-[11px] text-[var(--muted-2)]">
              Pulls the latest subscription state from the payment provider.
            </p>
          </div>
        </section>
      </div>

      {/* ── Checkout success banner ── */}
      {showBanner && (
        <div className="flex items-start justify-between gap-4 rounded-[12px] border border-emerald-500/30 bg-emerald-500/8 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="text-xl leading-none">🎉</span>
            <div>
              <p className="text-[13px] font-semibold text-foreground">
                You&apos;re on {plan.name}!
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--muted-text)]">
                Your models and render quotas have been updated.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setBannerDismissed(true)}
            className="shrink-0 text-[var(--muted-2)] transition-colors hover:text-foreground"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

// ─── shared page header ────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <header>
      <p className="mm-label">Billing</p>
      <h1 className="mt-1 text-[1.25rem] font-bold tracking-[-0.02em] text-foreground">
        Billing &amp; Usage
      </h1>
    </header>
  );
}

// ─── page export ──────────────────────────────────────────────────────────────

export default function BillingSettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <PageHeader />
          <div className="rounded-[12px] border border-[var(--chip-line)] bg-[var(--surface)] p-5">
            <p className="text-[13px] text-[var(--muted-2)]">
              Loading billing…
            </p>
          </div>
        </div>
      }
    >
      <BillingInner />
    </Suspense>
  );
}
