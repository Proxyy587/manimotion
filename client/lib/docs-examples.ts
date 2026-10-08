/** Shared multi-language API examples for docs. */

/** Official public API host */
export const MANIMOTION_API = "https://api.manimotion.dev";

export const CREATE_JOB = {
  curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "Explain Bayes theorem with a medical testing example",
    "style": "auto",
    "storage": {
      "inline": {
        "provider": "r2",
        "bucket": "my-lectures",
        "access_key_id": "'"$R2_ACCESS_KEY_ID"'",
        "secret_access_key": "'"$R2_SECRET_ACCESS_KEY"'",
        "account_id": "'"$R2_ACCOUNT_ID"'",
        "public_url": "'"$R2_PUBLIC_BASE_URL"'"
      }
    }
  }'`,
  javascript: `const res = await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "Explain Bayes theorem with a medical testing example",
    style: "auto",
    storage: {
      inline: {
        provider: "r2",
        bucket: process.env.R2_BUCKET_NAME,
        access_key_id: process.env.R2_ACCESS_KEY_ID,
        secret_access_key: process.env.R2_SECRET_ACCESS_KEY,
        account_id: process.env.R2_ACCOUNT_ID,
        public_url: process.env.R2_PUBLIC_BASE_URL,
      },
    },
  }),
});

const data = await res.json();
console.log(data);`,
  python: `import os, requests

API = os.environ["MANIMOTION_API"]
KEY = os.environ["MANIMOTION_KEY"]

r = requests.post(
    f"{API}/video/request",
    headers={
        "Content-Type": "application/json",
        "x-api-key": KEY,
    },
    json={
        "prompt": "Explain Bayes theorem with a medical testing example",
        "style": "auto",
        "storage": {
            "inline": {
                "provider": "r2",
                "bucket": os.environ["R2_BUCKET_NAME"],
                "access_key_id": os.environ["R2_ACCESS_KEY_ID"],
                "secret_access_key": os.environ["R2_SECRET_ACCESS_KEY"],
                "account_id": os.environ["R2_ACCOUNT_ID"],
                "public_url": os.environ["R2_PUBLIC_BASE_URL"],
            }
        },
    },
)
print(r.json())`,
};

export const CREATE_JOB_RESPONSE = `{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "cached": false,
  "video_url": null,
  "style": null
}`;

export const POLL_STATUS = {
  curl: `curl -sS "$MANIMOTION_API/video/status/$JOB_ID" \\
  -H "x-api-key: $MANIMOTION_KEY"`,
  javascript: `const st = await fetch(
  \`\${process.env.MANIMOTION_API}/video/status/\${jobId}\`,
  { headers: { "x-api-key": process.env.MANIMOTION_KEY } }
).then((r) => r.json());

console.log(st.status, st.video_url);`,
  python: `import os, requests

st = requests.get(
    f"{os.environ['MANIMOTION_API']}/video/status/{job_id}",
    headers={"x-api-key": os.environ["MANIMOTION_KEY"]},
).json()
print(st["status"], st.get("video_url"))`,
};

export const POLL_COMPLETED_RESPONSE = `{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "video_url": "https://cdn.example.com/videos/a1b2c3d4.mp4",
  "error": null,
  "cached": false,
  "style": "math",
  "duration": 54.2
}`;

export const POLL_FAILED_RESPONSE = `{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "failed",
  "video_url": null,
  "error": "We couldn't create this video. Try rephrasing the topic or making it more specific.",
  "cached": false,
  "style": "graphics",
  "duration": null
}`;

export const FULL_FLOW = {
  curl: `JOB=$(curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d "{
    \\"prompt\\": \\"Teach the product rule with a visual derivation\\",
    \\"storage\\": {
      \\"inline\\": {
        \\"provider\\": \\"r2\\",
        \\"bucket\\": \\"$R2_BUCKET_NAME\\",
        \\"access_key_id\\": \\"$R2_ACCESS_KEY_ID\\",
        \\"secret_access_key\\": \\"$R2_SECRET_ACCESS_KEY\\",
        \\"account_id\\": \\"$R2_ACCOUNT_ID\\",
        \\"public_url\\": \\"$R2_PUBLIC_BASE_URL\\"
      }
    }
  }" \\
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

echo "job=$JOB"
while true; do
  BODY=$(curl -sS "$MANIMOTION_API/video/status/$JOB" -H "x-api-key: $MANIMOTION_KEY")
  echo "$BODY"
  echo "$BODY" | grep -q '"status": "completed"' && break
  echo "$BODY" | grep -q '"status": "failed"' && exit 1
  sleep 3
done`,
  javascript: `const API = process.env.MANIMOTION_API;
const KEY = process.env.MANIMOTION_KEY;

async function generate(prompt) {
  const create = await fetch(\`\${API}/video/request\`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": KEY,
    },
    body: JSON.stringify({
      prompt,
      style: "auto",
      storage: {
        inline: {
          provider: "r2",
          bucket: process.env.R2_BUCKET_NAME,
          access_key_id: process.env.R2_ACCESS_KEY_ID,
          secret_access_key: process.env.R2_SECRET_ACCESS_KEY,
          account_id: process.env.R2_ACCOUNT_ID,
          public_url: process.env.R2_PUBLIC_BASE_URL,
        },
      },
    }),
  }).then((r) => r.json());

  if (!create.job_id) throw new Error(JSON.stringify(create));

  for (;;) {
    await new Promise((r) => setTimeout(r, 2500));
    const st = await fetch(\`\${API}/video/status/\${create.job_id}\`, {
      headers: { "x-api-key": KEY },
    }).then((r) => r.json());

    if (st.status === "completed") return st.video_url;
    if (st.status === "failed") throw new Error(st.error || "failed");
  }
}

const url = await generate("Teach the product rule with a visual derivation");
console.log(url);`,
  python: `import os, time, requests

API = os.environ["MANIMOTION_API"]
KEY = os.environ["MANIMOTION_KEY"]
H = {"x-api-key": KEY, "Content-Type": "application/json"}

create = requests.post(
    f"{API}/video/request",
    headers=H,
    json={
        "prompt": "Teach the product rule with a visual derivation",
        "storage": {
            "inline": {
                "provider": "r2",
                "bucket": os.environ["R2_BUCKET_NAME"],
                "access_key_id": os.environ["R2_ACCESS_KEY_ID"],
                "secret_access_key": os.environ["R2_SECRET_ACCESS_KEY"],
                "account_id": os.environ["R2_ACCOUNT_ID"],
                "public_url": os.environ["R2_PUBLIC_BASE_URL"],
            }
        },
    },
).json()
job_id = create["job_id"]

while True:
    time.sleep(2.5)
    st = requests.get(f"{API}/video/status/{job_id}", headers=H).json()
    if st["status"] == "completed":
        print(st["video_url"])
        break
    if st["status"] == "failed":
        raise SystemExit(st.get("error") or "failed")`,
};

export const STORAGE_INLINE_R2 = {
  curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "Explain Fourier series from waves to frequency",
    "storage": {
      "inline": {
        "provider": "r2",
        "bucket": "my-lectures",
        "access_key_id": "YOUR_R2_ACCESS_KEY",
        "secret_access_key": "YOUR_R2_SECRET",
        "account_id": "YOUR_CLOUDFLARE_ACCOUNT_ID",
        "public_url": "https://cdn.example.com"
      }
    }
  }'`,
  javascript: `const data = await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "Explain Fourier series from waves to frequency",
    storage: {
      inline: {
        provider: "r2",
        bucket: "my-lectures",
        access_key_id: process.env.R2_ACCESS_KEY_ID,
        secret_access_key: process.env.R2_SECRET_ACCESS_KEY,
        account_id: process.env.R2_ACCOUNT_ID,
        public_url: "https://cdn.example.com",
      },
    },
  }),
}).then((r) => r.json());

console.log(data.job_id);`,
  python: `import os, requests

r = requests.post(
    f"{os.environ['MANIMOTION_API']}/video/request",
    headers={
        "Content-Type": "application/json",
        "x-api-key": os.environ["MANIMOTION_KEY"],
    },
    json={
        "prompt": "Explain Fourier series from waves to frequency",
        "storage": {
            "inline": {
                "provider": "r2",
                "bucket": "my-lectures",
                "access_key_id": os.environ["R2_ACCESS_KEY_ID"],
                "secret_access_key": os.environ["R2_SECRET_ACCESS_KEY"],
                "account_id": os.environ["R2_ACCOUNT_ID"],
                "public_url": "https://cdn.example.com",
            }
        },
    },
)
print(r.json())`,
};

export const STORAGE_INLINE_S3 = {
  curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "Explain Bayes theorem",
    "storage": {
      "inline": {
        "provider": "s3",
        "bucket": "my-lectures",
        "access_key_id": "AKIA...",
        "secret_access_key": "...",
        "region": "us-east-1",
        "public_url": "https://cdn.example.com"
      }
    }
  }'`,
  javascript: `await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "Explain Bayes theorem",
    storage: {
      inline: {
        provider: "s3",
        bucket: process.env.S3_BUCKET,
        access_key_id: process.env.AWS_ACCESS_KEY_ID,
        secret_access_key: process.env.AWS_SECRET_ACCESS_KEY,
        region: "us-east-1",
        public_url: process.env.S3_PUBLIC_URL,
      },
    },
  }),
});`,
  python: `requests.post(
    f"{API}/video/request",
    headers={"Content-Type": "application/json", "x-api-key": KEY},
    json={
        "prompt": "Explain Bayes theorem",
        "storage": {
            "inline": {
                "provider": "s3",
                "bucket": "my-lectures",
                "access_key_id": "...",
                "secret_access_key": "...",
                "region": "us-east-1",
                "public_url": "https://cdn.example.com",
            }
        },
    },
)`,
};

export const STORAGE_MINIO = {
  curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "Timeline of the industrial revolution",
    "style": "graphics",
    "storage": {
      "inline": {
        "provider": "minio",
        "bucket": "lectures",
        "access_key_id": "minio",
        "secret_access_key": "minio123",
        "region": "us-east-1",
        "endpoint": "https://minio.example.com",
        "force_path_style": true,
        "public_url": "https://files.example.com"
      }
    }
  }'`,
  javascript: `await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "Timeline of the industrial revolution",
    style: "graphics",
    storage: {
      inline: {
        provider: "minio",
        bucket: "lectures",
        access_key_id: process.env.MINIO_KEY,
        secret_access_key: process.env.MINIO_SECRET,
        region: "us-east-1",
        endpoint: "https://minio.example.com",
        force_path_style: true,
        public_url: "https://files.example.com",
      },
    },
  }),
});`,
  python: `requests.post(
    f"{API}/video/request",
    headers={"Content-Type": "application/json", "x-api-key": KEY},
    json={
        "prompt": "Timeline of the industrial revolution",
        "style": "graphics",
        "storage": {
            "inline": {
                "provider": "minio",
                "bucket": "lectures",
                "access_key_id": "...",
                "secret_access_key": "...",
                "region": "us-east-1",
                "endpoint": "https://minio.example.com",
                "force_path_style": True,
                "public_url": "https://files.example.com",
            }
        },
    },
)`,
};

export const STORAGE_INTEGRATION = {
  curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "Visualize gradient descent",
    "storage": {
      "integration_id": "clxxxxxxxx"
    }
  }'`,
  javascript: `await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "Visualize gradient descent",
    storage: { integration_id: "clxxxxxxxx" },
  }),
}).then((r) => r.json());`,
  python: `requests.post(
    f"{API}/video/request",
    headers={"Content-Type": "application/json", "x-api-key": KEY},
    json={
        "prompt": "Visualize gradient descent",
        "storage": {"integration_id": "clxxxxxxxx"},
    },
)`,
};

export function asTabs(
  snippets: { curl: string; javascript: string; python: string },
  titles?: Partial<{ curl: string; javascript: string; python: string }>
) {
  return [
    { lang: "curl" as const, code: snippets.curl, title: titles?.curl },
    {
      lang: "javascript" as const,
      code: snippets.javascript,
      title: titles?.javascript,
    },
    { lang: "python" as const, code: snippets.python, title: titles?.python },
  ];
}
