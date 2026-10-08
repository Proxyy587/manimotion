import Link from "next/link";
import { ArrowUpRight, BookOpen, HardDrive, KeyRound } from "lucide-react";

export default function SettingsOverviewPage() {
  return (
    <div className="space-y-8">
      <header>
        <p className="mm-label">Overview</p>
        <h1 className="mt-1 text-[1.35rem] font-bold tracking-[-0.02em] text-foreground">
          Production setup
        </h1>
        <p className="mt-2 max-w-lg text-[13px] leading-relaxed text-[var(--muted-text)]">
          The home demo works without an account. Wire keys and storage when you
          call the worker from your own apps.
        </p>
      </header>

      <div className="grid overflow-hidden rounded-[12px] border border-[var(--chip-line)] sm:grid-cols-2">
        <Link
          href="/settings/api-keys"
          className="group block border-b border-[var(--chip-line)] bg-[var(--surface)] p-5 transition-colors hover:bg-[var(--chip)] sm:border-r sm:border-b-0"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] text-[var(--muted-2)]">01</p>
            <KeyRound
              className="size-4 text-[var(--muted-2)] transition-colors group-hover:text-foreground"
              strokeWidth={1.5}
            />
          </div>
          <h3 className="mt-4 text-[14px] font-bold tracking-tight text-foreground">
            API key
          </h3>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--muted-text)]">
            Authenticate with{" "}
            <code className="rounded-[5px] border border-[var(--chip-line)] bg-[var(--chip)] px-1 py-0.5 text-[var(--ink-soft)]">
              x-api-key
            </code>
            . Plaintext shown once — we store a hash only.
          </p>
          <span className="mt-4 inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)] group-hover:text-foreground">
            Create key <ArrowUpRight className="size-3" />
          </span>
        </Link>

        <Link
          href="/settings/storage"
          className="group block bg-[var(--surface)] p-5 transition-colors hover:bg-[var(--chip)]"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] text-[var(--muted-2)]">02</p>
            <HardDrive
              className="size-4 text-[var(--muted-2)] transition-colors group-hover:text-foreground"
              strokeWidth={1.5}
            />
          </div>
          <h3 className="mt-4 text-[14px] font-bold tracking-tight text-foreground">
            Storage
          </h3>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--muted-text)]">
            Save R2 / S3 credentials encrypted in the database. Worker decrypts
            only to upload.
          </p>
          <span className="mt-4 inline-flex items-center gap-1 text-[11px] text-[var(--ink-soft)] group-hover:text-foreground">
            Add bucket <ArrowUpRight className="size-3" />
          </span>
        </Link>
      </div>

      <Link
        href="/docs"
        className="flex items-center gap-3 rounded-[12px] border border-[var(--chip-line)] bg-[var(--surface)] p-4 transition-all hover:-translate-y-px hover:bg-[var(--chip)] hover:border-[var(--btn-hover-border)]"
      >
        <BookOpen
          className="size-4 text-[var(--ink-soft)]"
          strokeWidth={1.5}
        />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-foreground">
            Documentation
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--muted-text)]">
            Quickstart, API reference, storage, styles.
          </p>
        </div>
        <ArrowUpRight className="size-3.5 text-[var(--muted-2)]" />
      </Link>
    </div>
  );
}
