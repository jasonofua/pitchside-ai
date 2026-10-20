// Raw demo footage, recorded by Playwright: Three Fans on a goal, the Director panel's
// wrong-number and chaos-switch moments, and the recap. Voice-over is added afterwards.
//   node scripts/record-demo.mjs [base-url] [speed]
// Writes WebM files to web/recordings/. Uses the installed Chrome; run
// `pnpm exec playwright install ffmpeg` once for video encoding (Playwright offers no ffmpeg
// for macOS 13; there, screen-record with QuickTime or OBS following docs/VIDEO.md).
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:8000";
const speed = Number(process.argv[3] ?? 20);
const out = "recordings";
await mkdir(out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, init) {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "content-type": "application/json" },
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function waitFor(id, predicate, label) {
  for (;;) {
    const state = await api(`/api/matches/${id}/state`).catch(() => null);
    if (state && predicate(state)) return state;
    process.stdout.write(`\rwaiting for ${label}: ${state?.minute ?? "…"}   `);
    await sleep(2000);
  }
}

const { match_id: id } = await api("/api/matches", {
  method: "POST",
  body: JSON.stringify({ scenario: "comeback", speed, seed: 42 }),
});
console.log("match", id);

const browser = await chromium.launch({ channel: "chrome" });
const size = { width: 1920, height: 1080 };
const context = await browser.newContext({ viewport: size, recordVideo: { dir: out, size } });

// 1. Three Fans: the first goal, three stories.
const three = await context.newPage();
await three.goto(`${base}/three/?id=${id}`);
await waitFor(id, (s) => s.home.score + s.away.score >= 1, "the first goal");
await sleep(15_000);

// 2. Director: a wrong number for the Fact Checker, then the chaos switch.
const director = await context.newPage();
await director.goto(`${base}/director/?id=${id}`);
await sleep(4000);
await director.getByRole("button", { name: "Inject a wrong number" }).click();
await sleep(25_000);
await director.getByRole("button", { name: "Kill the Narrator" }).click();
await sleep(25_000);

// 3. Back to the screen for the comeback goals, then the recap at full time.
await three.bringToFront();
await waitFor(id, (s) => s.status === "full_time", "full time");
await sleep(8000);
const recap = await context.newPage();
await recap.goto(`${base}/recap/?id=${id}`);
await sleep(4000);
for (const lang of ["Pidgin", "Yorùbá", "Français"]) {
  await recap.getByRole("button", { name: lang }).click();
  await sleep(2500);
}
await context.close();
await browser.close();
console.log(`\nrecorded to web/${out}/`);
