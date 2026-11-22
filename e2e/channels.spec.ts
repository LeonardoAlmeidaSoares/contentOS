import { expect, test } from "@playwright/test";

const SCRIPT = "A casa ficava no fim da estrada, esquecida pelo tempo. Ninguém sabia quem a construiu. Em noites de chuva, uma luz acendia na janela mais alta. " +
  "Os moradores evitavam olhar para ela. Certa noite, um viajante bateu à porta e ouviu passos lentos do lado de dentro. " +
  "A porta se abriu sozinha, e o frio tomou conta do corredor. Ele entendeu tarde demais que não estava só e que alguém o observava.";

test("canal: criar padrão, aprovar, produzir dentro do padrão e ver a versão usada", async ({ page, request }) => {
  test.setTimeout(240_000);
  await page.goto("/fabricas/nova");
  await page.getByRole("button", { name: "Preencher manualmente" }).click();
  await page.getByTestId("f-name").fill("E2E Relatos");
  await page.getByTestId("f-niche").fill("histórias de terror");
  await page.getByTestId("min-horizontal").fill("10");
  await page.getByTestId("max-horizontal").fill("120");
  await page.getByTestId("f-forbidden").fill("gore");
  await page.getByTestId("confirm-create").click();
  await expect(page).toHaveURL(/fabricas\/[0-9a-f-]{36}\?aba=identidade$/);
  const lid = new URL(page.url()).pathname.split("/").pop()!;
  await expect(page.getByTestId("std-1").getByTestId("std-status")).toHaveText("Proposta");
  // sem versão aprovada não há produção
  await page.getByTestId("tab-producoes").click();
  await expect(page.getByText("Aprove uma versão do Padrão do Canal")).toBeVisible();
  await page.getByTestId("tab-identidade").click();
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("std-1").getByTestId("std-status")).toHaveText("Aprovada (vigente)");
  // nova versão preserva a anterior
  await page.getByTestId("new-version").click();
  await page.getByTestId("f-forbidden").fill("gore, sangue");
  await page.getByTestId("save-standard").click();
  await expect(page.getByTestId("std-2").getByTestId("std-status")).toHaveText("Proposta");
  await expect(page.getByTestId("std-1").getByTestId("std-status")).toHaveText("Aprovada (vigente)");
  await expect(page.getByTestId("std-2")).toContainText("Termos proibidos");
  // produção usa a v1 aprovada
  await page.getByTestId("tab-producoes").click();
  await page.getByTestId("p-topic").fill("A casa no fim da estrada");
  await page.getByRole("textbox", { name: /^Roteiro próprio/ }).fill(SCRIPT);
  await page.getByTestId("p-go").click();
  await expect(page).toHaveURL(/producao\//, { timeout: 30_000 });
  await expect(page.getByTestId("player")).toBeVisible({ timeout: 240_000 });
  await expect(page.getByTestId("production-validation")).toBeVisible({ timeout: 30_000 });
  const runs = await (await request.get(`/api/studio/factories/${lid}/channel`)).json();
  expect(runs.runs[0].standard_version).toBe(1);
  expect(runs.runs[0].validation.ok).toBe(true);
  await page.goto(`/fabricas/${lid}?aba=producoes`);
  await page.getByTestId("tab-producoes").click();
  await expect(page.getByTestId("production-card").first()).toContainText("Padrão v1");
  await page.getByTestId("production-card").first().click();
  await expect(page.getByTestId("production-validation")).toContainText("✓ resolução");
  await page.screenshot({ path: "../.cache/channels-center.png", fullPage: true });
});
