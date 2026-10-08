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
import {
  CREATE_JOB,
  CREATE_JOB_RESPONSE,
  asTabs,
} from "@/lib/docs-examples";
import { pageMetadata } from "@/lib/seo";
import { docsJsonLd } from "@/lib/docs-jsonld";
import { JsonLd } from "@/components/seo/json-ld";

export const metadata: Metadata = pageMetadata({
  title: "Introduction",
  description:
    "What is manimotion? Turn a STEM prompt into a narrated lecture video via HTTP — visuals, voice, and timing included.",
  path: "/docs",
  keywords: [
    "manimotion introduction",
    "text to lecture video",
    "educational video API overview",
  ],
});

const TOC = [
  { id: "what", label: "What is manimotion?" },
  { id: "flow", label: "Job lifecycle" },
  { id: "endpoints", label: "Endpoints" },
  { id: "taste", label: "Quick taste" },
  { id: "next", label: "Where to go next" },
];

export default function DocsIntroPage() {
  return (
    <DocShell toc={TOC} pageTitle="Introduction">
      <JsonLd
        data={docsJsonLd({
          title: "Introduction",
          description:
            "Turn a STEM prompt into a narrated lecture video via HTTP.",
          path: "/docs",
        })}
      />
      <p className="mm-label">Get started</p>
      <DocH1>Introduction</DocH1>
      <DocLead>
        manimotion is an HTTP API that turns a STEM prompt into a narrated
        lecture video. You send a topic; you get back an MP4 URL with
        narration and visuals timed together.
      </DocLead>

      <div className="mt-8 grid overflow-hidden rounded-[10px] border border-[var(--chip-line)] sm:grid-cols-2">
        {[
          {
            href: "/docs/quickstart",
            title: "Quickstart",
            body: "Key → request → poll → MP4 in under 5 minutes.",
          },
          {
            href: "/docs/api",
            title: "API reference",
            body: "Every field, status value, and error code.",
          },
          {
            href: "/docs/storage",
            title: "Storage",
            body: "Ship finished videos to your R2 / S3 bucket.",
          },
          {
            href: "/docs/styles",
            title: "Styles",
            body: "When to force math vs graphics vs auto.",
          },
        ].map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group block border-b border-r border-[var(--chip-line)] bg-[var(--surface)] p-5 transition-colors hover:bg-[var(--chip)] last:border-b-0 sm:odd:border-r sm:[&:nth-child(2)]:border-r-0 sm:[&:nth-child(3)]:border-b-0 sm:[&:nth-child(4)]:border-b-0 sm:[&:nth-child(4)]:border-r-0"
          >
            <p className="text-[13px] font-medium text-foreground">{card.title}</p>
            <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--muted-text)]">
              {card.body}
            </p>
          </Link>
        ))}
      </div>

      <DocH2 id="what">What is manimotion?</DocH2>
      <DocP>
        Think of it as “text → lecture video as a service.” Built for apps,
        tutors, and tools that need explainers on demand — not for editing
        timelines by hand.
      </DocP>
      <DocList>
        <li>Public API with an <code>x-api-key</code> header</li>
        <li>Async jobs (create, then poll)</li>
        <li>Math animations and motion-graphics explainers</li>
        <li>Optional BYO storage so MP4s land in your bucket</li>
      </DocList>

      <DocH2 id="flow">Job lifecycle</DocH2>
      <DocList>
        <li>
          <code>POST /video/request</code> returns a <code>job_id</code>
        </li>
        <li>
          Poll <code>/video/status/{"{job_id}"}</code> — <code>message</code>{" "}
          and <code>eta_seconds</code> show progress
        </li>
        <li>
          You get <code>video_url</code> when <code>status</code> is{" "}
          <code>completed</code>
        </li>
      </DocList>
      <div className="mt-4">
        <DocCallout title="Important" tone="accent">
          <p>
            The first response is <strong className="text-[var(--ink-soft)]">not</strong>{" "}
            the video. It is a <code>job_id</code>. Always poll{" "}
            <code>/video/status/{"{job_id}"}</code>.
          </p>
        </DocCallout>
      </div>

      <DocH2 id="endpoints">Endpoints (the whole public surface)</DocH2>
      <DocTable
        headers={["Method", "Path", "Purpose"]}
        rows={[
          ["POST", <code key="r">/video/request</code>, "Create a lecture job"],
          [
            "GET",
            <code key="s">/video/status/{"{job_id}"}</code>,
            "Poll status + video URL",
          ],
        ]}
      />

      <DocH2 id="taste">Quick taste</DocH2>
      <DocP>
        Switch language with the tabs. Every example also shows the response
        shape.
      </DocP>
      <CodeTabs
        className="mt-4"
        examples={asTabs(CREATE_JOB, {
          curl: "create.sh",
          javascript: "create.mjs",
          python: "create.py",
        })}
        response={CREATE_JOB_RESPONSE}
      />

      <DocH2 id="next">Where to go next</DocH2>
      <DocP>
        New to the API? Do the{" "}
        <Link
          href="/docs/quickstart"
          className="text-foreground underline-offset-2 hover:underline"
        >
          Quickstart
        </Link>
        . Building for real? Read the{" "}
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
