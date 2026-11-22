import { expect, test } from "@playwright/test";

const SCRIPT = "A casa ficava no fim da estrada, esquecida pelo tempo. Ninguém sabia quem a construiu. Em noites de chuva, uma luz acendia na janela mais alta. " +
  "Os moradores evitavam olhar para ela. Certa noite, um viajante bateu à porta e ouviu passos lentos do lado de dentro.";

test("início, instrução do Gemini e conversa sem chave (nada simulado)", async ({ page, request }) => {
  const st = await (await request.get("/api/studio/status")).json();
  if (st.gemini.configured) await page.route("**/api/studio/chat", route => route.fulfill({json:{status:"need_info",message:"Para qual público será o canal?",questions:[],proposal:null,usage:{input_tokens:0,output_tokens:0,cost:0}}}));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "O que você quer produzir hoje?" })).toBeVisible();
  await page.getByTestId("home-prompt").fill("Quero um canal de terror com vídeos de dez minutos");
  await page.getByTestId("home-go").click();
  await expect(page).toHaveURL(/fabricas\/nova/);
  if (!st.gemini.configured) {
    await expect(page.getByText("Gemini não configurado")).toBeVisible();
    await expect(page.getByTestId("confirm-create")).toHaveCount(0);
    await page.getByRole("link", { name: "Configurar assistente" }).click();
    await page.getByText("Como conectar o assistente", { exact: true }).click();
    await expect(page.getByText("GEMINI_API_KEY").first()).toBeVisible();
  } else {
    await expect(page.getByTestId("msg-assistant").first()).toBeVisible({ timeout: 60_000 });
  }
});

test("fábrica: produzir vídeo real, reproduzir e baixar", async ({ page, request }) => {
  test.setTimeout(240_000);
  const r = await request.post("/api/studio/factories", { data: { config: {
    name: "E2E Fábrica", theme: "abandoned house mystery", audience: "adultos", video_minutes: 1, frequency_per_week: 0,
    narrative_style: "sombria", visual_style: "fotos reais", voice: { engine: "piper", speed: 0.95, description: "Narrador grave" } } } });
  const { id } = await r.json();
  await page.goto(`/fabricas/${id}`);
  await expect(page.getByTestId("factory-name")).toHaveText("E2E Fábrica");
  await expect(page.getByTestId("proposal")).toContainText("abandoned house mystery");
  await page.getByTestId("topic").fill("A casa no fim da estrada");
  await page.getByTestId("own-script").check();
  await page.getByTestId("script-text").fill(SCRIPT);
  await page.getByTestId("produce").click();
  await expect(page).toHaveURL(/producao\//, { timeout: 30_000 });
  const player = page.getByTestId("player");
  await expect(player).toBeVisible({ timeout: 180_000 });
  await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.duration), { timeout: 30_000 }).toBeGreaterThan(5);
  const dl = await request.get((await page.getByTestId("download").getAttribute("href"))!);
  expect(dl.status()).toBe(200);
  expect((await dl.body()).subarray(4, 8).toString()).toBe("ftyp");
  await page.screenshot({ path: "../.cache/studio-production.png", fullPage: true });
  await page.goto(`/fabricas/${id}`);
  const materials = page.getByRole("region", { name: "Produção e materiais" });
  await expect(materials.getByRole("heading", { name: "Materiais do conteúdo" })).toBeVisible();
  await expect(materials.getByRole("list", { name: "Etapas da produção" }).getByRole("listitem")).toHaveCount(7);
  await materials.getByText("Ver roteiro", { exact: true }).click();
  await expect(materials.getByText(SCRIPT, { exact: true })).toBeVisible();
  await expect(materials.locator("audio")).toBeVisible();
  await expect(materials.getByRole("link", { name: "Abrir produção e todos os arquivos" })).toHaveAttribute("href", /producao\//);
});
