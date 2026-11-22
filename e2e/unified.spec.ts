import { expect, test } from "@playwright/test";

const SCRIPT = "A casa ficava no fim da estrada, esquecida pelo tempo. Ninguém sabia quem a construiu. Em noites de chuva, uma luz acendia na janela mais alta. Os moradores evitavam olhar para ela. Certa noite, um viajante bateu à porta e ouviu passos lentos do lado de dentro. A porta se abriu sozinha, e o frio tomou conta do corredor. Ele entendeu tarde demais que não estava só e que alguém o observava.";

test("integração: conversa, sugestões explícitas, aprovação e proposta de narrador", async ({ page, request }) => {
  test.setTimeout(180_000);
  const catalog = await (await request.get("/api/voices/providers")).json();
  const piper = catalog.providers.find((p: any) => p.id === "piper" && p.available);
  expect(piper?.voices.length).toBeGreaterThan(0);
  const config = {
    name: `E2E Integrada ${Date.now()}`, theme: "histórias de mistério", niche: "histórias de mistério", language: "pt-BR", tone: "documental",
    formats: [{ id: "horizontal", enabled: true, min_seconds: 10, max_seconds: 120 }, { id: "vertical", enabled: true, min_seconds: 10, max_seconds: 120 }],
    voice: { provider: "piper", voice_id: piper.voices[0].id, language: "pt-BR", fallback: false },
  };
  // Only the model response is intercepted. Creation, versioning, approval and audio use the real API.
  await page.route("**/api/studio/chat", route => route.fulfill({ json: {
    status: "ready", message: "Preparei uma proposta de canal para sua revisão.", questions: [],
    proposal: { config, preview: [{ label: "Nome da fábrica", value: config.name }], assumed: ["voz", "tom"] }, usage: { cost: 0, input_tokens: 0, output_tokens: 0 },
  } }));
  await page.goto("/fabricas/nova");
  await page.getByTestId("chat-input").fill("Quero um canal sobre histórias de mistério.");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("standard-form")).toContainText("sugerido pela IA");
  await page.getByTestId("confirm-create").click();
  await expect(page).toHaveURL(/fabricas\/[a-f0-9-]+\?aba=identidade$/);
  const id = new URL(page.url()).pathname.split("/").pop()!;
  await page.getByTestId("tab-producoes").click();
  await expect(page.getByText("Aprove uma versão do Padrão do Canal")).toBeVisible();
  await page.getByTestId("tab-identidade").click();
  const v1 = page.getByTestId("std-1");
  await v1.getByTestId("approve").click();
  await expect(v1).toContainText("confirme-os explicitamente");
  await v1.getByRole("checkbox", { name: "Confirmo as sugestões" }).check();
  await v1.getByTestId("approve").click();
  await expect(v1.getByTestId("std-status")).toHaveText("Aprovada (vigente)");
  await page.goto(`/vozes?fabrica=${id}`);
  await page.getByTestId("vl-provider").selectOption("piper");
  const voice = piper.voices[piper.voices.length - 1].id;
  await page.getByTestId("vl-voice").selectOption(voice);
  await page.getByTestId("vl-text").fill("Esta é uma amostra real da voz do nosso canal de mistérios.");
  await page.getByTestId("vl-generate").click();
  const sample = page.getByTestId("sample").first();
  await expect(sample).toContainText(voice, { timeout: 90_000 });
  const audio = sample.locator("audio");
  const audioResponse = await request.get((await audio.getAttribute("src"))!);
  expect(audioResponse.status()).toBe(200);
  expect((await audioResponse.body()).subarray(0, 4).toString()).toBe("RIFF");
  await audio.evaluate((a: HTMLAudioElement) => { a.load(); });
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.duration)).toBeGreaterThan(1);
  await sample.getByTestId("vl-use").click();
  await expect(page.getByText(/Narrador proposto na versão 2/)).toBeVisible();
  const before = await (await request.get(`/api/studio/factories/${id}/channel`)).json();
  expect(before.current.version).toBe(1);
  await page.getByRole("link", { name: "Revisar proposta →" }).click();
  await page.getByTestId("std-2").getByTestId("approve").click();
  await expect(page.getByTestId("std-2").getByTestId("std-status")).toHaveText("Aprovada (vigente)");
  const actual = await (await request.get(`/api/voices/factories/${id}`)).json();
  expect(actual.standard_version).toBe(2);
  expect(actual.voice_id).toBe(voice);
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `factory @ ${width}`).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "../.cache/unified-factory-identity.png", fullPage: true });
});

test("integração: produzir vídeo vertical real, reproduzir e proteger pilotos", async ({ page, request }) => {
  test.setTimeout(300_000);
  const cat = await (await request.get("/api/voices/providers")).json();
  const piper = cat.providers.find((p: any) => p.id === "piper" && p.available);
  const created = await request.post("/api/studio/channels", { data: { config: {
    name: `E2E Vertical ${Date.now()}`, theme: "abandoned house mystery", niche: "mistérios", language: "pt-BR",
    formats: [{ id: "vertical", enabled: true, min_seconds: 10, max_seconds: 120 }],
    editing: { resolution: "720p", subtitles: true, ken_burns: false },
    voice: { provider: "piper", voice_id: piper.voices[0].id, language: "pt-BR", fallback: false },
  } } });
  expect(created.status()).toBe(201);
  const { id, standard } = await created.json();
  expect((await request.post(`/api/studio/standards/${standard.id}/approve`, { data: {} })).status()).toBe(200);
  await page.goto(`/fabricas/${id}?aba=producoes`);
  await page.getByTestId("p-format").selectOption("vertical");
  await page.getByTestId("p-topic").fill("A casa no fim da estrada");
  await page.getByRole("textbox", { name: /^Roteiro próprio/ }).fill(SCRIPT);
  await page.getByTestId("p-go").click();
  await expect(page).toHaveURL(/producao\//, { timeout: 30_000 });
  const player = page.getByTestId("player");
  await expect(player).toBeVisible({ timeout: 240_000 });
  await expect(page.getByTestId("creative-version")).toContainText("Padrão criativo v1 · Vertical 9:16");
  await expect(page.getByTestId("production-validation")).toContainText("✓ proporção", { timeout: 30_000 });
  await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.videoHeight / v.videoWidth)).toBeCloseTo(16 / 9, 1);
  await player.evaluate(async (v: HTMLVideoElement) => { v.muted = true; await v.play(); });
  await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0);
  await page.screenshot({ path: "../.cache/unified-vertical-production.png", fullPage: true });
  expect((await request.post(`/api/lines/${id}/activate`)).status()).toBe(200);
  const blocked = await request.post(`/api/lines/${id}/run`);
  expect(blocked.status()).toBe(409);
  expect((await blocked.json()).detail).toContain("Padrão do Canal");
  const runs = await (await request.get("/api/runs")).json();
  const pilot = runs.find((r: any) => r.trigger === "pilot" && r.status === "succeeded");
  expect(pilot).toBeTruthy();
  await page.goto(`/producao/${pilot.id}`);
  await expect(page.getByText(/Não entra na aprovação editorial/)).toBeVisible();
  await expect(page.getByTestId("go-review")).toHaveCount(0);
  expect((await request.get(`/api/approvals/${pilot.id}`)).status()).toBe(404);
  expect((await request.post(`/api/approvals/${pilot.id}/decision`, { data: { decision: "approve", note: "não permitir" } })).status()).toBe(404);
  expect((await request.post(`/api/approvals/${pilot.id}/publish`, { data: { title: "Piloto", description: "", tags: [], made_for_kids: false, privacy: "private", confirm: true } })).status()).toBe(404);
});
