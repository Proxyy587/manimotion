import type { Metadata } from "next";
import Link from "next/link";

import { PLANS } from "@/lib/billing/plans";
import { LECTURE_MODELS } from "@/lib/chalkboard-api";
import { pageMetadata } from "@/lib/seo";
import { PricingActions } from "@/components/billing/pricing-actions";
import { ConsoleShell } from "@/components/layout/console-shell";

export const metadata: Metadata = pageMetadata({
  title: "Pricing",
  description:
    "manimotion pricing — free API with fast models. Hobby & Pro unlock GPT-4o, Claude Sonnet, and Opus for higher-quality STEM videos.",
  path: "/pricing",
  keywords: ["manimotion pricing", "STEM video pricing", "render subscription"],
});

// Models that are NEW on a given plan (not available on any lower tier).
function newModelsForPlan(planId: "FREE" | "HOBBY" | "PRO") {
  return LECTURE_MODELS.filter((m) => m.minPlan === planId);
}

// The "inherited" summary label for lower-tier models on a paid plan.
const inheritedLabel: Record<string, string> = {
  HOBBY: "All Free models",
  PRO: "All Hobby models",
};

const FAQ_ITEMS = [
  {
    q: "What counts as a render?",
    a: "Each video generation request counts as one render, regardless of video length or topic.",
  },
  {
    q: "Do unused renders roll over?",
    a: "No. Free renders reset at midnight UTC each day. Paid plan renders reset at the start of your billing month.",
  },
  {
    q: "Can I use my own OpenRouter key?",
    a: "Bring-Your-Own-Key is on the roadmap — coming soon.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes. Cancel from Settings → Billing at any time. Your plan stays active until the end of the current billing period.",
  },
  {
    q: "What's the difference between models?",
    a: "Free-tier models (Gemini Flash, DeepSeek) are fast but occasionally fail on complex topics. Hobby and Pro models (GPT-4o, Claude Sonnet 4.5, Claude Opus 4.1) produce richer visuals with noticeably fewer failures.",
  },
];

// Comparison table rows
const TABLE_ROWS: Array<{
  label: string;
  free: React.ReactNode;
  hobby: React.ReactNode;
  pro: React.ReactNode;
}> = [
  {
    label: "Renders / period",
    free: "3 / day",
    hobby: "40 / month",
    pro: "80 / month",
  },
  {
    label: "Resolution",
    free: "720p",
    hobby: "1080p",
    pro: "1080p",
  },
  {
    label: "Watermark",
    free: <span className="text-[var(--muted-2)]">Yes</span>,
    hobby: <span className="text-foreground font-medium">No</span>,
    pro: <span className="text-foreground font-medium">No</span>,
  },
  {
    label: "API access",
    free: <Check />,
    hobby: <Check />,
    pro: <Check />,
  },
  {
    label: "Queue priority",
    free: <span className="text-[var(--muted-2)]">Low</span>,
    hobby: <span className="text-foreground">Normal</span>,
    pro: <span className="text-foreground font-medium">Priority</span>,
  },
  {
    label: "Models",
    free: "Gemini 2.5 Flash, DeepSeek V3.2",
    hobby: "+ GPT-4o, Claude Sonnet 4.5",
    pro: "+ Claude Opus 4.1",
  },
];

function Check() {
  return <span className="text-foreground font-medium">✓</span>;
}

export default function PricingPage() {
  return (
    <ConsoleShell
      section="pricing"
      contentClassName="mx-auto w-full max-w-5xl px-5 py-10 md:px-8 md:py-14"
    >
      {/* Header */}
      <p className="mm-label">Pricing</p>
      <h1 className="mt-2 text-[2rem] font-bold tracking-[-0.02em] text-foreground md:text-[2.4rem]">
        Pay for renders.{" "}
        <span className="text-[var(--muted-text)]">
          Quality is the upgrade.
        </span>
      </h1>
      <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-[var(--muted-text)]">
        Free includes full API access with fast open models. Hobby and Pro
        unlock stronger models — Claude Sonnet and Opus produce richer visuals
        with fewer failures.
      </p>

      {/* Plan cards */}
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {PLANS.map((plan) => {
          const isHighlighted = !!plan.highlighted;
          const newModels = newModelsForPlan(plan.id);
          const inherited = inheritedLabel[plan.id];

          return (
            <article
              key={plan.id}
              className={[
                "relative flex flex-col rounded-[12px] border p-6 transition-shadow",
                isHighlighted
                  ? "border-foreground bg-[var(--surface)] shadow-[0_12px_40px_color-mix(in_oklab,var(--ink)_8%,transparent)]"
                  : "border-[var(--chip-line)] bg-[var(--surface)]",
              ].join(" ")}
            >
              {/* Most popular badge */}
              {isHighlighted && (
                <div className="absolute -top-px left-1/2 -translate-x-1/2">
                  <span className="inline-block rounded-b-[7px] bg-foreground px-3 py-0.5 text-[10px] font-semibold tracking-[0.06em] text-background">
                    MOST POPULAR
                  </span>
                </div>
              )}

              {/* Plan name */}
              <p className="text-[11px] font-semibold tracking-[0.08em] text-[var(--muted-2)]">
                {plan.name.toUpperCase()}
              </p>

              {/* Price */}
              <div className="mt-3 flex items-end gap-1">
                <span className="text-[2.25rem] font-bold leading-none tracking-tight text-foreground">
                  {plan.priceLabel}
                </span>
                {plan.priceUsd > 0 && (
                  <span className="mb-1 text-[13px] text-[var(--muted-text)]">
                    / mo
                  </span>
                )}
              </div>

              {/* Blurb */}
              <p className="mt-2 text-[13px] leading-relaxed text-[var(--muted-text)]">
                {plan.blurb}
              </p>

              {/* Renders quota — prominent */}
              <div className="mt-4 rounded-[8px] border border-[var(--chip-line)] bg-[var(--chip)] px-3 py-2">
                <p className="text-[13px] font-semibold text-foreground">
                  {plan.rendersLabel}
                </p>
                <p className="mt-0.5 text-[11px] text-[var(--muted-2)]">
                  {plan.id === "FREE"
                    ? "Resets daily at midnight UTC"
                    : "Resets each billing month"}
                </p>
              </div>

              {/* CTA */}
              <div className="mt-5">
                <PricingActions planId={plan.id} highlighted={isHighlighted} />
              </div>

              {/* Features */}
              <ul className="mt-5 flex-1 space-y-2">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-[13px]">
                    <span className="mt-0.5 shrink-0 text-[var(--muted-2)]">
                      ✓
                    </span>
                    <span className="text-[var(--ink-soft)]">{f}</span>
                  </li>
                ))}
              </ul>

              {/* Models section */}
              <div className="mt-5 border-t border-[var(--chip-line)] pt-4">
                <p className="text-[11px] font-medium tracking-[0.06em] text-[var(--muted-2)]">
                  MODELS
                </p>
                <ul className="mt-2 space-y-1.5">
                  {/* Inherited lower-tier summary */}
                  {inherited && (
                    <li className="flex items-center gap-2">
                      <span className="size-1.5 shrink-0 rounded-full bg-[var(--chip-line)]" />
                      <span className="text-[12px] text-[var(--muted-text)]">
                        {inherited}
                      </span>
                    </li>
                  )}
                  {/* New models on this plan — highlighted dot */}
                  {newModels.map((m) => (
                    <li key={m.id} className="flex items-center gap-2">
                      <span className="size-1.5 shrink-0 rounded-full bg-foreground" />
                      <span className="text-[12px] font-medium text-foreground">
                        {m.label}
                      </span>
                      {m.badge && (
                        <span className="ml-auto rounded-[5px] border border-[var(--chip-line)] bg-[var(--chip)] px-1.5 py-px text-[10px] text-[var(--muted-text)]">
                          {m.badge}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          );
        })}
      </div>

      {/* Comparison table */}
      <section className="mt-16">
        <p className="mm-label">Compare plans</p>
        <h2 className="mt-1.5 text-[1.15rem] font-bold tracking-tight text-foreground">
          Side by side
        </h2>

        <div className="mt-5 overflow-x-auto rounded-[12px] border border-[var(--chip-line)]">
          <table className="w-full min-w-[480px] border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-[var(--chip-line)] bg-[var(--chip)]">
                <th className="px-4 py-3 text-left text-[11px] font-semibold tracking-[0.06em] text-[var(--muted-2)]">
                  FEATURE
                </th>
                {PLANS.map((p) => (
                  <th
                    key={p.id}
                    className={[
                      "px-4 py-3 text-left text-[11px] font-semibold tracking-[0.06em]",
                      p.highlighted
                        ? "text-foreground"
                        : "text-[var(--muted-2)]",
                    ].join(" ")}
                  >
                    {p.name.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-[var(--surface)]">
              {TABLE_ROWS.map((row, i) => (
                <tr
                  key={row.label}
                  className={
                    i < TABLE_ROWS.length - 1
                      ? "border-b border-[var(--chip-line)]"
                      : ""
                  }
                >
                  <td className="px-4 py-3 font-medium text-[var(--ink-soft)]">
                    {row.label}
                  </td>
                  <td className="px-4 py-3 text-[var(--muted-text)]">
                    {row.free}
                  </td>
                  <td className="px-4 py-3 text-[var(--muted-text)]">
                    {row.hobby}
                  </td>
                  <td className="px-4 py-3 text-[var(--muted-text)]">
                    {row.pro}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* FAQ */}
      <section className="mt-16">
        <p className="mm-label">FAQ</p>
        <h2 className="mt-1.5 text-[1.15rem] font-bold tracking-tight text-foreground">
          Common questions
        </h2>

        <dl className="mt-5 space-y-px overflow-hidden rounded-[12px] border border-[var(--chip-line)]">
          {FAQ_ITEMS.map((item, i) => (
            <div
              key={item.q}
              className={[
                "bg-[var(--surface)] px-5 py-4",
                i < FAQ_ITEMS.length - 1
                  ? "border-b border-[var(--chip-line)]"
                  : "",
              ].join(" ")}
            >
              <dt className="text-[13px] font-semibold text-foreground">
                {item.q}
              </dt>
              <dd className="mt-1.5 text-[13px] leading-relaxed text-[var(--muted-text)]">
                {item.a}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Footer nudge */}
      <p className="mt-10 text-[12px] text-[var(--muted-2)]">
        Questions?{" "}
        <Link
          href="/docs"
          className="text-[var(--muted-text)] underline underline-offset-2 hover:text-foreground transition-colors"
        >
          Read the docs
        </Link>{" "}
        or open an issue on GitHub.
      </p>
    </ConsoleShell>
  );
}
