"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const DOCS_NAV = [
  {
    group: "Get started",
    items: [
      { href: "/docs", label: "Introduction" },
      { href: "/docs/quickstart", label: "Quickstart" },
    ],
  },
  {
    group: "API",
    items: [
      { href: "/docs/api", label: "Reference" },
      { href: "/docs/storage", label: "Storage" },
      { href: "/docs/styles", label: "Styles" },
    ],
  },
] as const;

export function DocsSideNav() {
  const pathname = usePathname();

  return (
    <nav className="space-y-6">
      {DOCS_NAV.map((section) => (
        <div key={section.group}>
          <p className="mb-2 px-2 text-[11px] font-medium text-[var(--muted-2)]">
            {section.group}
          </p>
          <ul className="space-y-0.5">
            {section.items.map((item) => {
              const active =
                item.href === "/docs"
                  ? pathname === "/docs"
                  : pathname === item.href ||
                    pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "block rounded-[8px] px-2.5 py-1.5 text-[13px] transition-colors",
                      active
                        ? "bg-[var(--chip)] font-medium text-foreground"
                        : "text-[var(--muted-text)] hover:bg-[var(--chip)] hover:text-foreground"
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
