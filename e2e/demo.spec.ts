import { expect, test } from "@playwright/test";

test("menu inicial e áreas indisponíveis", async ({ page }) => {
  await page.goto("/");
  for (const l of ["Visão Geral", "Linhas de Produção", "Execuções", "Biblioteca", "Provedores", "Configurações"])
    await expect(page.getByRole("link", { name: l })).toBeVisible();
  await page.getByRole("link", { name: "Provedores" }).click();
  await expect(page.getByText("Ainda não disponível")).toBeVisible();
});

test("fluxo demonstrativo: execução, progresso, artefato e download", async ({ page }) => {
  await page.goto("/execucoes");
  await page.getByTestId("start-run").click();
  await expect(page).toHaveURL(/\/execucoes\/.+/);
  await expect(page.getByTestId("step")).toHaveCount(3);
  await expect(page.getByText("Concluída").first()).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download").click()]);
  expect(download.suggestedFilename()).toBe("demo-output.json");
  const body = JSON.parse(require("fs").readFileSync(await download.path(), "utf8"));
  expect(body.items).toHaveLength(5);
});
