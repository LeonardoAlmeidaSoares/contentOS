import { Page, expect, test } from "@playwright/test";
import { readFileSync } from "fs";

const uid = () => Math.random().toString(36).slice(2, 7);

async function createLine(page: Page, name: string, config: object, extra: Record<string, string> = {}) {
  await page.goto("/linhas/nova");
  await page.getByTestId("f-name").fill(name);
  await page.getByTestId("f-config").fill(JSON.stringify(config));
  if (extra.limMonth) await page.getByTestId("f-limmonth").fill(extra.limMonth);
  await page.getByTestId("save-line").click();
  await expect(page.getByTestId("line-title")).toHaveText(name);
}

test("menu inicial e áreas indisponíveis", async ({ page }) => {
  await page.goto("/");
  for (const l of ["Visão Geral", "Linhas de Produção", "Execuções", "Biblioteca", "Provedores", "Configurações"])
    await expect(page.getByRole("link", { name: l })).toBeVisible();
  await page.getByRole("link", { name: "Provedores" }).click();
  await expect(page.getByText("Ainda não disponível")).toBeVisible();
});

test("linha: criar, ativar, executar, acompanhar e baixar artefato", async ({ page }) => {
  const name = `E2E ${uid()}`;
  await createLine(page, name, { step_delay: 0.5, cost_per_step: 0.25 });
  await expect(page.getByTestId("run-line")).toBeDisabled(); // inativa
  await page.getByTestId("toggle-line").click();
  await expect(page.getByTestId("run-line")).toBeEnabled();
  await page.getByTestId("run-line").click();
  await expect(page).toHaveURL(/\/execucoes\/.+/);
  await expect(page.getByTestId("step")).toHaveCount(3);
  await expect(page.getByText("Concluída").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("US$ 0.75").first()).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download").click()]);
  expect(download.suggestedFilename()).toBe("demo-output.json");
  expect(JSON.parse(readFileSync(await download.path(), "utf8")).items).toHaveLength(5);
  // histórico e produtos na página da linha
  await page.getByRole("link", { name: /←/ }).click();
  await expect(page.getByTestId("run-row")).toHaveCount(1);
  await expect(page.getByText("demo-output.json")).toBeVisible();
});

test("falha e retomada pela interface", async ({ page }) => {
  await createLine(page, `Falha ${uid()}`, { step_delay: 0.2, fail_step: "process", fail_attempts: 3 });
  await page.getByTestId("toggle-line").click();
  await page.getByTestId("run-line").click();
  // max_attempts padrão = 3, backoff 5s+10s → falha definitiva na 3ª tentativa
  await expect(page.getByTestId("run-error")).toContainText("process", { timeout: 45_000 });
  await expect(page.getByTestId("resume-run")).toBeVisible();
  await page.getByTestId("resume-run").click();
  await expect(page.getByText("Concluída").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("download")).toBeVisible();
});

test("orçamento mensal bloqueia nova execução", async ({ page }) => {
  await createLine(page, `Orc ${uid()}`, { step_delay: 0.1, cost_per_step: 1 }, { limMonth: "2" });
  await page.getByTestId("toggle-line").click();
  await page.getByTestId("run-line").click();
  await expect(page.getByTestId("run-error")).toContainText("orçamento", { timeout: 30_000 });
  await page.getByRole("link", { name: /←/ }).click();
  await page.getByTestId("run-line").click();
  await expect(page.getByTestId("action-error")).toContainText("mensal");
});
