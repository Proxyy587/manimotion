import type { Metadata } from "next";
import Link from "next/link";

import { CodeTabs } from "@/components/docs/code-tabs";
import {
  DocCallout,
  DocH1,
  DocH2,
  DocLead,
  DocList,
  DocP,
  DocShell,
  DocTable,
} from "@/components/docs/doc-primitives";
import { CREATE_JOB_RESPONSE, asTabs } from "@/lib/docs-examples";
import { pageMetadata } from "@/lib/seo";
import { docsJsonLd } from "@/lib/docs-jsonld";
import { JsonLd } from "@/components/seo/json-ld";

export const metadata: Metadata = pageMetadata({
  title: "Styles",
  description:
    "Choose math, graphics, or auto for manimotion lecture videos — when to force each visual style.",
  path: "/docs/styles",
  keywords: ["math animation API", "explainer video style", "lecture video style"],
});

const TOC = [
  { id: "pick", label: "Which style?" },
  { id: "auto", label: "auto" },
  { id: "math", label: "math" },
  { id: "graphics", label: "graphics" },
  { id: "tips", label: "Tips" },
];

function styleExample(prompt: string, style: string, file: string) {
  return asTabs(
    {
      curl: `curl -sS -X POST "$MANIMOTION_API/video/request" \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $MANIMOTION_KEY" \\
  -d '{
    "prompt": "${prompt}",
    "style": "${style}"
  }'`,
      javascript: `await fetch(\`\${process.env.MANIMOTION_API}/video/request\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "x-api-key": process.env.MANIMOTION_KEY,
  },
  body: JSON.stringify({
    prompt: "${prompt}",
    style: "${style}",
  }),
}).then((r) => r.json());`,
      python: `requests.post(
    f"{API}/video/request",
    headers={"Content-Type": "application/json", "x-api-key": KEY},
    json={
        "prompt": "${prompt}",
        "style": "${style}",
    },
).json()`,
    },
    { curl: `${file}.sh`, javascript: `${file}.mjs`, python: `${file}.py` },
  );
}

export default function DocsStylesPage() {
  return (
    <DocShell toc={TOC} pageTitle="Styles">
      <JsonLd
        data={docsJsonLd({
          title: "Styles",
          description: "Math vs graphics vs auto for lecture videos.",
          path: "/docs/styles",
        })}
      />
      <p className="mm-label">API</p>
      <DocH1>Styles</DocH1>
      <DocLead>
        Two visual styles, one API. Pass <code>style</code> on{" "}
        <code>POST /video/request</code>, or leave it on <code>auto</code>.
      </DocLead>

      <DocH2 id="pick">Which style?</DocH2>
      <DocTable
        headers={["style", "Best for"]}
        rows={[
          [<code key="a">auto</code>, "Default. Picked from your prompt."],
          [<code key="m">math</code>, "Equations, graphs, physics, geometric proofs"],
          [
            <code key="g">graphics</code>,
            "Charts, timelines, cards, typography-heavy explainers",
          ],
        ]}
      />

      <DocH2 id="auto">auto</DocH2>
      <DocP>
        Use this unless you already know. A 12-step derivation belongs in{" "}
        <code>math</code>; a product comparison belongs in{" "}
        <code>graphics</code>.
      </DocP>

      <DocH2 id="math">math</DocH2>
      <DocList>
        <li>Equations that transform step by step</li>
        <li>Coordinate planes, vectors, graphs</li>
        <li>Geometry and trigonometry demos</li>
      </DocList>
      <CodeTabs
        className="mt-4"
        examples={styleExample(
          "Derive the quadratic formula step by step",
          "math",
          "math",
        )}
        response={CREATE_JOB_RESPONSE}
      />

      <DocH2 id="graphics">graphics</DocH2>
      <DocList>
        <li>Bar and line charts that grow with the narration</li>
        <li>Timelines and process diagrams</li>
        <li>Card stacks, comparisons, UI-style explainers</li>
      </DocList>
      <CodeTabs
        className="mt-4"
        examples={styleExample(
          "Compare HTTP vs WebSockets with a clean timeline of use cases",
          "graphics",
          "graphics",
        )}
        response={CREATE_JOB_RESPONSE}
      />

      <DocH2 id="tips">Tips</DocH2>
      <div className="mt-4">
        <DocCallout title="Tip" tone="default">
          <p>
            If a job fails on a “soft” topic (history, product UX), retry with{" "}
            <code>style: &quot;graphics&quot;</code>. For heavy math, force{" "}
            <code>math</code>.
          </p>
        </DocCallout>
      </div>
      <DocP>
        Full request fields →{" "}
        <Link
          href="/docs/api"
          className="text-foreground underline-offset-2 hover:underline"
        >
          API reference
        </Link>
        .
      </DocP>
    </DocShell>
  );
}
