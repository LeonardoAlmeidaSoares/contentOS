import { expect, test } from "@playwright/test";

const routes: [string, string][] = [["/", "O que você quer produzir hoje?"], ["/fabricas", "Minhas Fábricas"], ["/fabricas/nova", "Criar Fábrica com IA"], ["/producoes", "Produções"], ["/aprovacoes", "Aprovações"], ["/publicacoes", "Publicações"], ["/biblioteca", "Biblioteca"], ["/configuracoes", "Configurações"]];

test("Studio: navegação e responsividade em desktop e celular", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [route, heading] of routes) {
      await page.goto(route);
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${route} @ ${width}`).toBe(true);
    }
  }
  await page.getByRole("button", { name: "Abrir menu" }).click();
  await page.getByRole("link", { name: "Minhas Fábricas", exact: true }).click();
  await expect(page).toHaveURL(/\/fabricas$/);
  await expect(page.getByRole("button", { name: "Abrir menu" })).toHaveAttribute("aria-expanded", "false");
  expect(errors).toEqual([]);
});

test("fábricas reais: capas por identidade, busca e abertura do projeto", async ({ page, request }) => {
  const suffix = Date.now();
  const factories = [];
  for (const [name, theme] of [[`E2E Cosmos ${suffix}`, "astronomia e universo"], [`E2E Nocturne ${suffix}`, "histórias de terror"]]) {
    const r = await request.post("/api/studio/factories", { data: { config: { name, theme, audience: "adultos", video_minutes: 5, frequency_per_week: 0, narrative_style: "documental", visual_style: "cinematográfico", voice: { engine: "piper", speed: 1, description: "Narração natural" } } } });
    expect(r.status()).toBe(201);
    factories.push(await r.json());
  }
  await page.goto("/fabricas");
  const search = page.getByRole("textbox", { name: "Buscar fábricas" });
  await search.fill(`E2E Cosmos ${suffix}`);
  await expect(page.getByTestId("factory-card")).toHaveCount(1);
  await expect(page.locator(".cover-cosmos")).toHaveCount(1);
  await search.fill(`E2E Nocturne ${suffix}`);
  await expect(page.locator(".cover-nocturne")).toHaveCount(1);
  await search.fill("não existe uma fábrica com este nome");
  await expect(page.getByText("Nenhuma fábrica encontrada")).toBeVisible();
  await search.fill(`E2E Cosmos ${suffix}`);
  await page.getByTestId("factory-card").click();
  await expect(page).toHaveURL(new RegExp(`/fabricas/${factories[0].id}`));
  await expect(page.getByTestId("factory-name")).toHaveText(`E2E Cosmos ${suffix}`);
  await expect(page.getByTestId("proposal")).toContainText("astronomia e universo");
  await expect(page.getByTestId("toggle-auto")).toBeDisabled();
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.screenshot({ path: "../.cache/factory-mobile.png", fullPage: true });
});

test("biblioteca e produções: seleção real e busca sem resultados", async ({ page, request }) => {
  const artifacts = await (await request.get("/api/artifacts")).json();
  const image = artifacts.find((a: {content_type:string})=>a.content_type.startsWith("image/"));
  await page.goto("/biblioteca");
  if (image) {
    await page.getByRole("button", { name: /^Imagens/ }).click();
    await page.locator(".collection-layout > div > article").first().getByRole("button", { name: "Detalhes" }).click();
    await expect(page.locator("#library-preview").getByRole("img", { name: image.filename, exact: true })).toHaveAttribute("src", new RegExp(image.id));
    await expect(page.locator("#library-preview").getByRole("heading", { level: 2 })).toHaveText(image.filename);
    const download = await request.get(`/api/artifacts/${image.id}/download`);
    expect(download.status()).toBe(200);
    await page.getByRole("button", { name: /^Todos/ }).click();
  }
  await page.getByRole("textbox", {name:"Buscar arquivos"}).fill("arquivo-inexistente-e2e-999");
  await expect(page.getByRole("heading", {name:/Nenhum arquivo encontrado|Um espaço para suas criações/})).toBeVisible();
  await page.goto("/producoes");
  await page.getByRole("textbox", {name:"Buscar produções"}).fill("producao-inexistente-e2e-999");
  await expect(page.getByRole("heading", {name:/Nenhuma produção encontrada|Sua próxima ideia começa aqui/})).toBeVisible();
});

test("falha de rede é visível e carregamento não apresenta dados inventados", async ({page}) => {
  await page.route("**/api/lines", route => route.abort("failed"));
  await page.goto("/fabricas");
  await expect(page.getByRole("alert")).toContainText("Não foi possível carregar as fábricas");
  await expect(page.getByTestId("factory-card")).toHaveCount(0);
  await page.unroute("**/api/lines");
  await page.route("**/api/lines", async route => {
    await new Promise(resolve => setTimeout(resolve, 1200));
    await route.continue();
  });
  await page.reload();
  await expect(page.getByRole("status", {name:"Carregando"})).toBeVisible();
  await page.unroute("**/api/lines");
});

test("assistente: pergunta, prévia e confirmação criam fábrica real (resposta de IA simulada só no teste)", async ({page, request}) => {
  const config = { name: `E2E Conversa ${Date.now()}`, theme: "mistérios do universo", audience: "adultos", video_minutes: 10, frequency_per_week: 0, narrative_style: "documental", visual_style: "cinematográfico", voice: { engine: "piper", speed: 1, description: "Narração natural" } };
  const history: {role:string;content:string}[][] = [];
  await page.route("**/api/studio/chat", async route => {
    history.push(route.request().postDataJSON().messages);
    await route.fulfill({json: {
      status: history.length === 1 ? "need_info" : "ready",
      message: history.length === 1 ? "Vamos criar um canal de astronomia." : "Sua identidade criativa está pronta para revisão.",
      questions: history.length === 1 ? ["Para qual público você quer produzir?"] : [],
      proposal: history.length === 1 ? null : {config, preview:[{label:"Nome da fábrica",value:config.name},{label:"Tema",value:config.theme}]},
      usage: {input_tokens:null,output_tokens:null,cost:0},
    }});
  });
  await page.goto("/fabricas/nova");
  await page.getByTestId("chat-input").fill("Quero um canal sobre os mistérios do universo com vídeos de 10 minutos.");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("msg-assistant")).toContainText("Para qual público");
  await expect(page.getByTestId("confirm-create")).toHaveCount(0);
  await page.getByTestId("chat-input").fill("Para adultos curiosos, com narração documental.");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("proposal")).toContainText(config.name);
  expect(history[1].map(m=>m.role)).toEqual(["user","assistant","user"]);
  const before = await (await request.get("/api/lines")).json();
  expect(before.some((f: {name:string})=>f.name === config.name)).toBe(false);
  await page.getByTestId("confirm-create").click();
  await expect(page).toHaveURL(/\/fabricas\/[a-f0-9-]+$/);
  await expect(page.getByTestId("factory-name")).toHaveText(config.name);
  const id = new URL(page.url()).pathname.split("/").pop();
  const factory = await (await request.get(`/api/studio/factories/${id}`)).json();
  expect(factory.config.theme).toBe(config.theme);
});
