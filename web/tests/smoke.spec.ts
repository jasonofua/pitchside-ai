import { expect, test } from "@playwright/test";

// Start a match from the home page, personalise, and see live data and cards arrive.
test("a judge can start a demo match and watch it", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Every fan saw the same goal/ })).toBeVisible();
  await page.getByRole("button", { name: "20×" }).click();
  await page.getByRole("button", { name: "Start demo match" }).click();
  await page.waitForURL(/\/match\/\?id=/);

  await expect(page.getByRole("dialog", { name: "Personalize your match" })).toBeVisible();
  await page.getByRole("button", { name: /Casual fan/ }).click();
  await page.getByRole("button", { name: "Pidgin" }).click();
  await page.getByRole("button", { name: "Watch" }).click();

  // The clock runs and the pitch is drawn.
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByText(/LIVE/)).toBeVisible({ timeout: 30_000 });
  const clock = page.locator(".display.tnum").filter({ hasText: /^\d{2}:\d{2}$/ }).first();
  const first = await clock.textContent();
  await expect.poll(async () => clock.textContent(), { timeout: 20_000 }).not.toBe(first);

  // A card arrives for this viewer (a player tag, ticker, lower third or stat bug card).
  await expect(page.getByText(/dey fly|correct pass|Chance wey big|Game don turn|dey press|GOAL/i).first())
    .toBeVisible({ timeout: 60_000 });
  expect(errors).toEqual([]);
});

test("the Three Fans view shows three profiles side by side", async ({ page, request }) => {
  const res = await request.post("/api/matches", { data: { scenario: "comeback", speed: 20 } });
  const { match_id } = (await res.json()) as { match_id: string };
  await page.goto(`/three/?id=${match_id}`);
  await expect(page.getByText("Analyst · English")).toBeVisible();
  await expect(page.getByText("Casual fan · Pidgin")).toBeVisible();
  await expect(page.getByText("Player Cam · Yorùbá")).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(3);
});
