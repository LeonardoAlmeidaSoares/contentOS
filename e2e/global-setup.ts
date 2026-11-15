import { request } from "@playwright/test";
import { readFileSync } from "fs";

export default async function setup() {
  const base = process.env.BASE_URL ?? "http://192.168.18.2:8300";
  let token = process.env.ADMIN_TOKEN;
  if (!token) token = readFileSync("../.env", "utf8").match(/^ADMIN_TOKEN=(.+)$/m)?.[1];
  if (!token) throw new Error("defina ADMIN_TOKEN (ou ../.env)");
  const ctx = await request.newContext({ baseURL: base });
  const r = await ctx.post("/api/auth/login", { data: { token } });
  if (!r.ok()) throw new Error(`login falhou: ${r.status()}`);
  await ctx.storageState({ path: ".auth.json" });
}
