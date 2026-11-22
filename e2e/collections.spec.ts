import { expect, test } from "@playwright/test";

test("produções: filtrar uma fábrica real, ordenar e alternar a visualização", async ({page,request}) => {
  const runs=(await (await request.get('/api/runs')).json()).filter((r:{pipeline:string})=>r.pipeline==='video_youtube');
  test.skip(!runs.length,'Nenhuma produção de vídeo disponível');
  const factory=runs[0].line_id;
  const expected=runs.filter((r:{line_id:string})=>r.line_id===factory).sort((a:{created_at:string},b:{created_at:string})=>a.created_at.localeCompare(b.created_at));
  await page.goto('/producoes');
  await page.getByRole('combobox',{name:'Filtrar por fábrica',exact:true}).selectOption(factory);
  await expect(page.getByTestId('production-card')).toHaveCount(expected.length);
  await page.getByRole('button',{name:'Lista',exact:true}).click();
  await expect(page.locator('.production-list')).toBeVisible();
  await page.getByRole('combobox',{name:'Ordenar produções'}).selectOption('oldest');
  await expect(page.getByTestId('production-card').first()).toHaveAttribute('href',`/producao/${expected[0].id}`);
  await page.getByTestId('production-card').first().click();
  await expect(page.getByTestId('prod-title')).toBeVisible();
});

test("materiais: roteiro e arquivos pertencem à produção selecionada", async ({page,request}) => {
  const list=await (await request.get('/api/approvals?status=all')).json();
  test.skip(!list.length,'Nenhuma produção concluída disponível');
  const run=await (await request.get(`/api/runs/${list[0].run_id}`)).json();
  await page.goto(`/producao/${run.id}`);
  const materials=page.getByRole('region',{name:'Materiais e arquivos da produção'});
  await materials.getByRole('button',{name:'Roteiro',exact:true}).click();
  const section=run.steps.find((s:{name:string})=>s.name==='script')?.output?.sections?.[0];
  const text=section?.text??section?.scenes?.[0]?.narration;
  if(text) await expect(materials).toContainText(text);
  await materials.getByRole('button',{name:/^Imagens/}).click();
  await expect(materials.locator('article')).toHaveCount(run.artifacts.filter((a:{content_type:string})=>a.content_type.startsWith('image/')).length);
  const image=run.artifacts.find((a:{content_type:string})=>a.content_type.startsWith('image/'));
  if(image) expect((await request.get(`/api/artifacts/${image.id}/download`)).status()).toBe(200);
});

test("publicações: calendário consulta datas sem oferecer agendamento", async ({page}) => {
  await page.goto('/publicacoes');
  await page.getByRole('button',{name:'Calendário',exact:true}).click();
  const calendar=page.getByRole('region',{name:'Calendário de envios'});
  const month=await calendar.getByRole('heading',{level:2}).textContent();
  await calendar.getByRole('button',{name:'Mês anterior'}).click();
  await expect(calendar.getByRole('heading',{level:2})).not.toHaveText(month!);
  await calendar.getByRole('button',{name:'Próximo mês'}).click();
  await expect(calendar.getByRole('heading',{level:2})).toHaveText(month!);
  const day=calendar.locator('.calendar-day').nth(18);
  const date=(await day.getAttribute('aria-label'))!.split(',')[0];
  await day.click();
  await expect(calendar.getByRole('heading',{level:3})).toHaveText(date);
  await expect(calendar).toContainText('agendamento editorial ainda não está disponível');
  await expect(page.getByRole('button',{name:/Agendar publicação/})).toHaveCount(0);
});

test("configurações: provedores reais e preferência de movimento persistente", async ({page,request}) => {
  const providers=await (await request.get('/api/providers')).json();
  await page.goto('/configuracoes');
  await page.getByRole('button',{name:'Provedores',exact:true}).click();
  await expect(page.getByRole('article')).toHaveCount(providers.length);
  await page.getByRole('button',{name:'Preferências',exact:true}).click();
  await page.getByRole('combobox',{name:'Preferência de animações'}).selectOption('reduced');
  await expect(page.locator('html')).toHaveAttribute('data-motion','reduced');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-motion','reduced');
  await page.getByRole('button',{name:'Preferências',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Preferência de animações'})).toHaveValue('reduced');
  await page.getByRole('combobox',{name:'Preferência de animações'}).selectOption('system');
  await page.getByRole('button',{name:'Avançado',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Disponibilidade do estúdio'})).toBeVisible();
  await expect(page.getByText('Banco de dados',{exact:true})).toBeVisible();
});
