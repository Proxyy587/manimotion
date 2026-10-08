"use client";

import { Copy, Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { setStoredApiKey } from "@/lib/chalkboard-api";
import { useMountEffect } from "@/hooks/use-mount-effect";
import { readJsonSafe } from "@/lib/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  environment: string;
  plan: string;
  usageCount: number;
  lastUsedAt: string | null;
};

export default function ApiKeysSettingsPage() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/api-keys");
      const data = await readJsonSafe<{ error?: string; keys?: ApiKeyRow[] }>(res);
      if (!res.ok) throw new Error(data.error ?? "Failed to load keys");
      setKeys(data.keys ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useMountEffect(() => {
    void load();
  });

  async function createKey() {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), environment: "live" }),
      });
      const data = await readJsonSafe<{ error?: string; key?: string }>(res);
      if (!res.ok) throw new Error(data.error ?? "Create failed");
      setCreatedKey(data.key ?? null);
      setName("");
      toast.success("API key created");
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Create failed";
      setError(msg);
      toast.error(msg);
    } finally {
      setCreating(false);
    }
  }

  async function confirmRevoke() {
    if (!revokeTarget) return;
    const target = revokeTarget;
    setRevokeTarget(null);
    const res = await fetch(`/api/api-keys/${target.id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await readJsonSafe<{ error?: string }>(res);
      toast.error(data.error ?? "Revoke failed");
      return;
    }
    toast.success(`Revoked “${target.name}”`);
    await load();
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="mm-label">Credentials</p>
        <h1 className="mt-1 text-[1.25rem] font-semibold tracking-tight text-foreground">
          API keys
        </h1>
        <p className="mt-2 text-[13px] text-[var(--muted-text)]">
          Send{" "}
          <code className="border border-[var(--chip-line)] bg-[var(--bg)] px-1.5 py-0.5 text-[11px] text-[var(--muted-text)]">
            x-api-key: chalk_live_sk_v1_…
          </code>{" "}
          on every worker request.
        </p>
      </header>

      <section className="rounded-[10px] border border-[var(--chip-line)] bg-[var(--surface)] p-4">
        <Label htmlFor="key-name">New key name</Label>
        <div className="mt-2 flex flex-wrap gap-2">
          <Input
            id="key-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Production"
            className="max-w-xs"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void createKey();
              }
            }}
          />
          <button
            type="button"
            className="mm-pixel-btn inline-flex items-center gap-1.5 px-3 py-2 disabled:opacity-40"
            onClick={() => void createKey()}
            disabled={creating || !name.trim()}
          >
            <Plus className="size-3.5" />
            {creating ? "Creating…" : "Create"}
          </button>
        </div>
        {error && <p className="mt-2 text-[12px] text-red-400">{error}</p>}
      </section>

      <section className="divide-y divide-border overflow-hidden rounded-[10px] border border-[var(--chip-line)]">
        <div className="flex items-center justify-between px-4 py-2.5">
          <p className="text-[11px] font-medium tracking-[0.08em] text-[var(--muted-2)]">
            ACTIVE KEYS
          </p>
          <p className="text-[11px] tabular-nums text-[var(--muted-2)]">{keys.length}</p>
        </div>
        {loading && <p className="p-6 text-[12px] text-[var(--muted-2)]">Loading…</p>}
        {!loading && keys.length === 0 && (
          <p className="p-6 text-[12px] text-[var(--muted-2)]">
            No keys yet — create one above.
          </p>
        )}
        {keys.map((key) => (
          <div
            key={key.id}
            className="flex items-center justify-between gap-4 px-4 py-3.5"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] text-[var(--ink-soft)]">{key.name}</span>
                <Badge variant="outline">{key.environment}</Badge>
                <Badge variant="default">{key.plan}</Badge>
              </div>
              <p className="mt-1 text-[11px] text-[var(--muted-2)]">
                <code>{key.prefix}…</code> · {key.usageCount} requests
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-red-400"
              aria-label={`Revoke API key ${key.name}`}
              title={`Revoke ${key.name}`}
              onClick={() => setRevokeTarget(key)}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
      </section>

      <Dialog
        open={createdKey != null}
        onOpenChange={(open) => {
          if (!open) setCreatedKey(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your API key</DialogTitle>
            <DialogDescription>
              This secret is shown once. Store it somewhere safe, then optionally
              use it in this browser for the demo.
            </DialogDescription>
          </DialogHeader>
          <code className="block break-all rounded-[9px] border border-[var(--chip-line)] bg-[var(--chip)] p-3 text-[12px] text-[var(--ink-soft)]">
            {createdKey}
          </code>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                if (!createdKey) return;
                void navigator.clipboard.writeText(createdKey);
                toast.success("Copied");
              }}
            >
              <Copy className="size-3.5" /> Copy
            </Button>
            <Button
              type="button"
              onClick={() => {
                if (!createdKey) return;
                setStoredApiKey(createdKey);
                setCreatedKey(null);
                toast.success("Saved for this browser");
              }}
            >
              Use in this browser
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={revokeTarget != null}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key?</AlertDialogTitle>
            <AlertDialogDescription>
              “{revokeTarget?.name}” will stop working immediately. This cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500/15 text-red-400 hover:bg-red-500/25"
              onClick={() => void confirmRevoke()}
            >
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
