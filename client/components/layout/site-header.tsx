"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AccountMenu } from "@/components/account/account-menu";
import { GitHubStarButton } from "@/components/layout/github-star-button";
import { ThemeToggle } from "@/components/theme/theme-provider";
import { useSession } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

type Section = "home" | "docs" | "settings" | "pricing";

/**
 * Shared top bar for docs / settings / pricing / home.
 * Same chrome everywhere — only the active section label + right links change.
 *
 * `reveal` — home only: slides in on scroll (matches former lp-topbar motion).
 */
export function SiteHeader({
  section,
  reveal,
  revealed,
  className,
}: {
  section: Section;
  reveal?: boolean;
  revealed?: boolean;
  className?: string;
}) {
  const pathname = usePathname();
  const { data: session } = useSession();

  const sectionLabel =
    section === "docs"
      ? "Docs"
      : section === "settings"
        ? "Settings"
        : section === "pricing"
          ? "Pricing"
          : null;

  return (
    <header
      className={cn(
        "flex h-14 items-center justify-between gap-4 border-b border-border bg-background px-4 md:px-6",
        reveal
          ? cn(
              "lp-site-header fixed inset-x-0 top-0 z-[55]",
              revealed && "show"
            )
          : "shrink-0",
        className
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <Link href="/" className="mm-brand truncate text-[13px]">
          manimotion
        </Link>
        {sectionLabel && (
          <>
            <span className="hidden h-3 w-px bg-border sm:block" />
            <span className="hidden text-[11px] text-[var(--muted-2)] sm:inline">
              {sectionLabel}
            </span>
          </>
        )}
      </div>

      <nav className="flex items-center gap-1 sm:gap-2">
        <HeaderLink href="/docs" active={pathname.startsWith("/docs")}>
          Docs
        </HeaderLink>
        <HeaderLink href="/pricing" active={pathname.startsWith("/pricing")}>
          Pricing
        </HeaderLink>
        <HeaderLink
          href="/settings"
          active={pathname.startsWith("/settings")}
        >
          Settings
        </HeaderLink>
        <GitHubStarButton className="ml-1" />
        {!reveal && <ThemeToggle />}
        {session?.user ? (
          <AccountMenu />
        ) : (
          <Link
            href="/sign-in"
            className="ml-1 text-[12px] text-[var(--muted-text)] transition-colors hover:text-foreground"
          >
            Sign in
          </Link>
        )}
        {reveal && revealed && <ThemeToggle />}
      </nav>
    </header>
  );
}

function HeaderLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-[7px] px-2 py-1.5 text-[12px] transition-colors",
        active
          ? "bg-[var(--chip)] font-medium text-foreground"
          : "text-[var(--muted-text)] hover:text-foreground"
      )}
    >
      {children}
    </Link>
  );
}
