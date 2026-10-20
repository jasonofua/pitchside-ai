// Screenshot tour of the app against a running gateway (default http://localhost:8000).
// Uses the locally installed Chrome, so no browser download is needed:
//   node scripts/shots.mjs [base-url] [out-dir]
import { mkdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:8000";
const out = process.argv[3] ?? "shots";
await mkdir(out, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
page.on("console", (m) => m.type() === "error" && console.log("console error:", m.text()));
page.on("pageerror", (e) => console.log("page error:", e.message));

await page.goto(base, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/1-home.png` });

await page.getByRole("button", { name: "20×" }).click();
await page.getByRole("button", { name: "Start demo match" }).click();
await page.waitForURL(/\/match\/\?id=/);
const matchUrl = page.url();
const id = new URL(matchUrl).searchParams.get("id");
console.log("match", id);
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/2-onboarding.png` });
await page.getByRole("button", { name: /Casual fan/ }).click();
await page.getByRole("button", { name: "Pidgin" }).click();
await page.getByRole("button", { name: "Watch" }).click();
await page.waitForTimeout(14000);
await page.screenshot({ path: `${out}/3-match.png` });
await page.waitForTimeout(12000);
await page.screenshot({ path: `${out}/4-match-later.png` });

const three = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
three.on("pageerror", (e) => console.log("three page error:", e.message));
await three.goto(`${base}/three/?id=${id}`, { waitUntil: "networkidle" });
await three.waitForTimeout(12000);
await three.screenshot({ path: `${out}/5-three.png` });

const director = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await director.goto(`${base}/director/?id=${id}`, { waitUntil: "networkidle" });
await director.waitForTimeout(6000);
await director.screenshot({ path: `${out}/6-director.png` });

const analyst = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await analyst.goto(`${base}/analyst/?id=${id}`, { waitUntil: "networkidle" });
await analyst.waitForTimeout(3000);
await analyst.screenshot({ path: `${out}/7-analyst.png`, fullPage: true });

const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
await phone.goto(`${base}/match/?id=${id}`, { waitUntil: "networkidle" });
await phone.waitForTimeout(4000);
await phone.screenshot({ path: `${out}/8-phone.png`, fullPage: true });

await browser.close();
console.log("done");
