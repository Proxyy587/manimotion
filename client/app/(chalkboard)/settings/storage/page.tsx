"use client";

import { Plus, Trash2, RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMountEffect } from "@/hooks/use-mount-effect";
import { readJsonSafe } from "@/lib/http";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

type Provider = "R2" | "S3" | "UPLOADTHING" | "MINIO" | "CUSTOM_S3" | "BACKBLAZE";

type Integration = {
  id: string;
  name: string;
  provider: Provider;
  bucketName: string;
  region: string | null;
  publicUrl: string | null;
  isVerified: boolean;
  createdAt: string;
};

const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "R2", label: "Cloudflare R2" },
  { id: "S3", label: "AWS S3" },
  { id: "UPLOADTHING", label: "UploadThing" },
  { id: "MINIO", label: "MinIO" },
  { id: "CUSTOM_S3", label: "S3-compatible" },
  { id: "BACKBLAZE", label: "Backblaze B2" },
];

export default function StorageSettingsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [provider, setProvider] = useState<Provider>("R2");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [removeId, setRemoveId] = useState<string | null>(null);

  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [accountId, setAccountId] = useState("");
  const [bucketName, setBucketName] = useState("");
  const [region, setRegion] = useState("auto");
  const [endpoint, setEndpoint] = useState("");
  const [publicUrl, setPublicUrl] = useState("");
  const [uploadThingToken, setUploadThingToken] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/storage");
      const data = await readJsonSafe(res);
      if (!res.ok) {
        throw new Error(
          typeof data.error === "string" ? data.error : "Failed to load"
        );
      }
      setIntegrations(
        Array.isArray(data.integrations)
          ? (data.integrations as Integration[])
          : []
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useMountEffect(() => {
    void load();
  });

  function buildPayload() {
    if (provider === "UPLOADTHING") {
      return {
        provider,
        name: name.trim(),
        config: { token: uploadThingToken.trim() },
      };
    }
    if (provider === "R2") {
      return {
        provider,
        name: name.trim(),
        config: {
          accessKeyId: accessKeyId.trim(),
          secretAccessKey: secretAccessKey.trim(),
          accountId: accountId.trim(),
          bucketName: bucketName.trim(),
          publicUrl: publicUrl.trim() || undefined,
        },
      };
    }
    return {
      provider,
      name: name.trim(),
      config: {
        accessKeyId: accessKeyId.trim(),
        secretAccessKey: secretAccessKey.trim(),
        region: region.trim() || "us-east-1",
        bucketName: bucketName.trim(),
        endpoint: endpoint.trim() || undefined,
        publicUrl: publicUrl.trim() || undefined,
        forcePathStyle: provider === "MINIO" || provider === "CUSTOM_S3",
      },
    };
  }

  async function saveIntegration() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/storage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await readJsonSafe(res);
      if (!res.ok) {
        throw new Error(
          typeof data.error === "string" ? data.error : "Save failed"
        );
      }
      setShowForm(false);
      setName("");
      setAccessKeyId("");
      setSecretAccessKey("");
      setAccountId("");
      setBucketName("");
      setUploadThingToken("");
      toast.success("Storage saved");
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Save failed";
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  async function confirmRemove() {
    if (!removeId) return;
    const id = removeId;
    setRemoveId(null);
    const res = await fetch(`/api/storage/${id}`, { method: "DELETE" });
    if (!res.ok) {
      toast.error("Remove failed");
      return;
    }
    toast.success("Storage removed");
    await load();
  }

  async function test(id: string) {
    const res = await fetch(`/api/storage/${id}`, { method: "POST" });
    const data = await readJsonSafe(res);
    if (data.success) {
      toast.success("Connection OK");
      await load();
    } else {
      toast.error(
        typeof data.error === "string" ? data.error : "Connection failed"
      );
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mm-label">Buckets</p>
          <h1 className="mt-1 text-[1.25rem] font-semibold tracking-tight text-foreground">
            Storage
          </h1>
          <p className="mt-2 max-w-lg text-[13px] text-[var(--muted-text)]">
            Credentials are encrypted (AES-256-GCM) before they hit the
            database. Secrets are never returned by the API — only metadata.
          </p>
        </div>
        <Button type="button" onClick={() => setShowForm(true)}>
          <Plus className="size-3.5" />
          Add storage
        </Button>
      </div>

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add storage</DialogTitle>
            <DialogDescription>
              Connect R2, S3, or another compatible bucket. We encrypt credentials
              at rest; the worker decrypts only to upload.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4">
            <div>
              <Label htmlFor="storage-name">Name</Label>
              <Input
                id="storage-name"
                className="mt-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My R2 bucket"
              />
            </div>
            <div>
              <Label htmlFor="storage-provider">Provider</Label>
              <Select
                value={provider}
                onValueChange={(v) => setProvider(v as Provider)}
              >
                <SelectTrigger id="storage-provider" className="mt-2 w-full" aria-label="Storage provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {provider === "UPLOADTHING" ? (
              <div>
                <Label htmlFor="storage-ut-token">API token</Label>
                <Input
                  id="storage-ut-token"
                  className="mt-2"
                  type="password"
                  value={uploadThingToken}
                  onChange={(e) => setUploadThingToken(e.target.value)}
                />
              </div>
            ) : provider === "R2" ? (
              <>
                <div>
                  <Label htmlFor="storage-account-id">Account ID</Label>
                  <Input
                    id="storage-account-id"
                    className="mt-2"
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-access-key">Access key ID</Label>
                  <Input
                    id="storage-access-key"
                    className="mt-2"
                    value={accessKeyId}
                    onChange={(e) => setAccessKeyId(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-secret-key">Secret access key</Label>
                  <Input
                    id="storage-secret-key"
                    className="mt-2"
                    type="password"
                    value={secretAccessKey}
                    onChange={(e) => setSecretAccessKey(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-bucket">Bucket</Label>
                  <Input
                    id="storage-bucket"
                    className="mt-2"
                    value={bucketName}
                    onChange={(e) => setBucketName(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-public-url">Public URL (optional)</Label>
                  <Input
                    id="storage-public-url"
                    className="mt-2"
                    value={publicUrl}
                    onChange={(e) => setPublicUrl(e.target.value)}
                    placeholder="https://cdn.example.com"
                  />
                </div>
              </>
            ) : (
              <>
                <div>
                  <Label htmlFor="storage-access-key-s3">Access key ID</Label>
                  <Input
                    id="storage-access-key-s3"
                    className="mt-2"
                    value={accessKeyId}
                    onChange={(e) => setAccessKeyId(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-secret-key-s3">Secret access key</Label>
                  <Input
                    id="storage-secret-key-s3"
                    className="mt-2"
                    type="password"
                    value={secretAccessKey}
                    onChange={(e) => setSecretAccessKey(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-bucket-s3">Bucket</Label>
                  <Input
                    id="storage-bucket-s3"
                    className="mt-2"
                    value={bucketName}
                    onChange={(e) => setBucketName(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-region">Region</Label>
                  <Input
                    id="storage-region"
                    className="mt-2"
                    value={region}
                    onChange={(e) => setRegion(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-endpoint">Endpoint (optional)</Label>
                  <Input
                    id="storage-endpoint"
                    className="mt-2"
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="storage-public-url-s3">Public URL (optional)</Label>
                  <Input
                    id="storage-public-url-s3"
                    className="mt-2"
                    value={publicUrl}
                    onChange={(e) => setPublicUrl(e.target.value)}
                  />
                </div>
              </>
            )}
            {error && (
              <p className="text-[12px] text-red-400" role="alert">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={saving || !name.trim()}
              onClick={() => void saveIntegration()}
            >
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <section className="divide-y divide-border overflow-hidden rounded-[10px] border border-[var(--chip-line)]">
        <div className="flex items-center justify-between px-4 py-2.5">
          <p className="text-[11px] font-medium tracking-[0.08em] text-[var(--muted-2)]">
            INTEGRATIONS
          </p>
          <p className="text-[11px] text-[var(--muted-2)]">
            Copy an id → pass as{" "}
            <code className="text-[var(--muted-text)]">storage.integration_id</code>
          </p>
        </div>
        {loading && <p className="p-6 text-[12px] text-[var(--muted-2)]">Loading…</p>}
        {!loading && integrations.length === 0 && (
          <p className="p-6 text-[12px] text-[var(--muted-2)]">
            No storage yet — add a bucket to upload finished lectures.
          </p>
        )}
        {integrations.map((row) => (
          <div
            key={row.id}
            className="flex items-center justify-between gap-4 px-4 py-3.5"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] text-[var(--ink-soft)]">{row.name}</span>
                <Badge variant="outline">{row.provider}</Badge>
                {row.isVerified && <Badge variant="default">verified</Badge>}
              </div>
              <p className="mt-1 truncate text-[11px] text-[var(--muted-2)]">
                <code className="text-[var(--muted-text)]">{row.id}</code>
                {row.bucketName ? ` · ${row.bucketName}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  void navigator.clipboard.writeText(row.id);
                  toast.success("Integration id copied");
                }}
              >
                Copy id
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Test storage ${row.name}`}
                title="Test connection"
                onClick={() => void test(row.id)}
              >
                <RefreshCw className="size-3.5" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-red-400"
                aria-label={`Remove storage ${row.name}`}
                title={`Remove ${row.name}`}
                onClick={() => setRemoveId(row.id)}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </section>

      <AlertDialog
        open={removeId != null}
        onOpenChange={(open) => {
          if (!open) setRemoveId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove storage?</AlertDialogTitle>
            <AlertDialogDescription>
              Existing videos stay in your bucket. New jobs will use the default
              worker storage unless you pass another integration.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500/15 text-red-400 hover:bg-red-500/25"
              onClick={() => void confirmRemove()}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
