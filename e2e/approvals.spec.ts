import { expect, test } from "@playwright/test";

// Usa a produção real mais recente concluída (MP4 já gerado). Não publica nada: só revisão.
test("aprovações: revisar, decidir e confirmar que aprovar não publica", async ({ page, request }) => {
  const all = await (await request.get("/api/approvals?status=all")).json();
  test.skip(all.length === 0, "nenhuma produção concluída");
  const item = all[0];
  await page.goto("/aprovacoes");
  await expect(page.getByRole("heading", { name: "Aprovações" })).toBeVisible();
  await page.getByTestId("tab-" + item.review.status).click();
  await page.getByTestId("approval-card").first().click();
  await expect(page.getByTestId("player")).toBeVisible();
  await expect.poll(() => page.getByTestId("player").evaluate((v: HTMLVideoElement) => v.duration), { timeout: 30_000 }).toBeGreaterThan(5);
  await page.getByTestId("note").fill("Revisão e2e: narração precisa melhorar");
  await page.getByTestId("request-changes").click();
  await expect(page.getByTestId("review-status")).toContainText("Alterações solicitadas");
  await expect(page.getByTestId("open-publish")).toHaveCount(0); // bloqueado
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("review-status")).toContainText("Aprovada");
  await expect(page.getByTestId("events")).toContainText("aprovada");
  await expect(page.getByTestId("pub-row")).toHaveCount(0); // aprovar não publica
  const d = await (await request.get(`/api/approvals/${item.run_id}`)).json();
  expect(d.publications).toHaveLength(0);
  if (!(await (await request.get("/api/youtube/status")).json()).channel) {
    await expect(page.getByText(/Conecte um canal|ainda não foi configurada/)).toBeVisible();
    await expect(page.getByTestId("open-publish")).toHaveCount(0);
  }
});

test("configurações: YouTube exibe estado real e instrução", async ({ page, request }) => {
  const st = await (await request.get("/api/youtube/status")).json();
  await page.goto("/configuracoes");
  if (!st.configured) await expect(page.getByText("Credenciais do Google ainda não configuradas")).toBeVisible();
  await expect(page.getByTestId("yt-status")).toBeVisible();
});
