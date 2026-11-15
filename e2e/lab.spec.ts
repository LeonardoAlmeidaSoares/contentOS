import { expect, test } from "@playwright/test";

test("provedores: cadastro sem vazar credencial, teste e ativação", async ({ page }) => {
  const secret = "sk-E2E-SECRET-0123456789abcdef";
  await page.goto("/provedores/novo");
  await page.getByTestId("p-service").selectOption("openai");
  await page.getByTestId("p-name").fill("OpenAI E2E");
  await page.getByTestId("p-key").fill(secret);
  await page.getByTestId("save-provider").click();
  await expect(page.getByTestId("provider-title")).toHaveText("OpenAI E2E");
  expect(await page.content()).not.toContain(secret);
  await expect(page.getByText("…cdef")).toBeVisible();
  await page.getByTestId("toggle-provider").click();
  await expect(page.getByText("Ativa", { exact: true })).toBeVisible();
  await page.getByTestId("toggle-provider").click();         // deixa inativo: nenhuma chamada paga em testes
  await expect(page.getByText("Inativa", { exact: true })).toBeVisible();
  const api = await page.request.get("/api/providers");
  expect(await api.text()).not.toContain(secret);
});

test("laboratório: comparar modelos (simulados), avaliar e consultar histórico", async ({ page }) => {
  await page.goto("/laboratorio/imagens");
  await page.getByTestId("lab-prompt").fill("um gato fofo para colorir [e2e]");
  await page.getByTestId("target-mock-image-free").check({ force: true });
  await page.getByTestId("target-mock-image-paid").check({ force: true });
  await expect(page.getByTestId("estimate-total")).toHaveText("US$ 0.25");
  await page.getByTestId("lab-run").click();
  await expect(page.getByTestId("result-card")).toHaveCount(2);
  await expect(page.getByTestId("result-image")).toHaveCount(2, { timeout: 30_000 });
  for (const img of await page.getByTestId("result-image").all())
    expect(await img.evaluate((e: HTMLImageElement) => e.naturalWidth)).toBeGreaterThan(0);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("result-download").first().click()]);
  expect(download.suggestedFilename()).toMatch(/\.png$/);
  await page.getByTestId("rate-4").first().click();
  await page.getByTestId("result-notes").first().fill("linhas boas");
  await page.getByTestId("result-notes").first().blur();
  await page.getByRole("link", { name: "Histórico", exact: true }).click();
  await expect(page.getByTestId("exp-row").first()).toContainText("★4");
  await page.getByTestId("exp-row").first().click();
  await expect(page.getByTestId("result-notes").first()).toHaveValue("linhas boas");
});

test("laboratório: custo desconhecido exige autorização explícita", async ({ page }) => {
  await page.goto("/laboratorio/imagens");
  await page.getByTestId("lab-prompt").fill("teste sem preço");
  await page.getByTestId("target-mock-image-nopricing").check({ force: true });
  await expect(page.getByTestId("lab-run")).toBeDisabled();
  await page.getByTestId("allow-unknown").check();
  await expect(page.getByTestId("lab-run")).toBeEnabled();
});

test("laboratório: texto em modelo simulado", async ({ page }) => {
  await page.goto("/laboratorio/texto");
  await page.getByTestId("lab-prompt").fill("diga olá");
  await page.getByTestId("target-mock-text").check({ force: true });
  await page.getByTestId("lab-run").click();
  await expect(page.getByTestId("result-text")).toContainText("diga olá", { timeout: 30_000 });
});

test("benchmark: preparado, exige confirmação e não executa sozinho", async ({ page }) => {
  await page.goto("/laboratorio/benchmark");
  await expect(page.getByTestId("bench-prompt")).toHaveCount(5);
  await page.getByTestId("target-mock-image-paid").check({ force: true });
  await expect(page.getByTestId("bench-total")).toHaveText("US$ 1.25");
  await expect(page.getByTestId("bench-run")).toBeDisabled();
  await page.getByTestId("bench-confirm").check();
  await expect(page.getByTestId("bench-run")).toBeEnabled();      // não clicamos: evita gerar lote (mesmo simulado)
});
