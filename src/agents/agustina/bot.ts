import { Bot, InlineKeyboard } from 'grammy';
import 'dotenv/config';

const token = process.env.TELEGRAM_BOT_TOKEN;
if (!token) {
  console.log('TELEGRAM_BOT_TOKEN no configurado - bot en standby.');
  process.exit(0);
}

const API = 'http://127.0.0.1:3000';
const bot = new Bot(token);

bot.command('start', (ctx) => ctx.reply('Hola! Soy Agustina. Mandame /vender para registrar una venta, o /stock para ver el stock actual.'));
bot.command('ayuda', (ctx) => ctx.reply('Comandos:\n/vender - registrar una venta\n/stock - ver stock actual'));

bot.command('vender', async (ctx) => {
  const res = await fetch(`${API}/products`);
  const items = await res.json();
  const active = items.filter((p: any) => p.status === 'active');
  if (!active.length) return ctx.reply('No hay productos cargados todavia.');
  const kb = new InlineKeyboard();
  for (const p of active) kb.text(`${p.name} (${p.code ?? 's/c'})`, `prod:${p.id}`).row();
  await ctx.reply('Que se vendio?', { reply_markup: kb });
});

bot.command('stock', async (ctx) => {
  const res = await fetch(`${API}/products`);
  const items = await res.json();
  const lines = items.map((p: any) => `${p.code ?? '?'} - ${p.name}: ${p.stockQuantity} unidades`);
  await ctx.reply(lines.join('\n') || 'Sin productos cargados.');
});

bot.callbackQuery(/^prod:(.+)$/, async (ctx) => {
  const productId = ctx.match[1];
  const res = await fetch(`${API}/products/${productId}/variants`);
  const variants = await res.json();
  await ctx.answerCallbackQuery();
  if (!variants.length) return ctx.reply('Ese producto no tiene talles cargados.');
  const kb = new InlineKeyboard();
  for (const v of variants) kb.text(`${v.size} (${v.stockQuantity} disp.)`, `size:${productId}:${v.id}`).row();
  await ctx.reply('Que talle?', { reply_markup: kb });
});

bot.callbackQuery(/^size:(.+):(.+)$/, async (ctx) => {
  const [, productId, variantId] = ctx.match;
  await ctx.answerCallbackQuery();
  const kb = new InlineKeyboard();
  for (let n = 1; n <= 5; n++) kb.text(`${n}`, `qty:${productId}:${variantId}:${n}`);
  await ctx.reply('Cuantas unidades?', { reply_markup: kb });
});

bot.callbackQuery(/^qty:(.+):(.+):(\d+)$/, async (ctx) => {
  const [, productId, variantId, qtyStr] = ctx.match;
  const quantity = parseInt(qtyStr, 10);
  const product = await (await fetch(`${API}/products/${productId}`)).json();
  const unitPrice = Number(product.price ?? 0);
  const orderRes = await fetch(`${API}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel: 'in_person', items: [{ productId, productVariantId: variantId, quantity, unitPrice }] }),
  });
  const { order } = await orderRes.json();
  await ctx.answerCallbackQuery({ text: 'Venta registrada!' });
  await ctx.reply(`Listo! Registre ${quantity} unidad(es) de ${product.name}. Total: $${order.total}`);
});

bot.command('reponer', async (ctx) => {
  const res = await fetch(`${API}/products`);
  const items = await res.json();
  if (!items.length) return ctx.reply('No hay productos cargados todavia.');
  const kb = new InlineKeyboard();
  for (const p of items) kb.text(`${p.name} (${p.code ?? 's/c'})`, `rprod:${p.id}`).row();
  await ctx.reply('A que producto le entra mercaderia?', { reply_markup: kb });
});

bot.callbackQuery(/^rprod:(.+)$/, async (ctx) => {
  const productId = ctx.match[1];
  await ctx.answerCallbackQuery();
  const variants = await (await fetch(`${API}/products/${productId}/variants`)).json();
  const kb = new InlineKeyboard();
  const known = new Set(variants.map((v: any) => v.size));
  for (const v of variants) kb.text(`${v.size} (${v.stockQuantity} actual)`, `rsize:${productId}:${v.size}`).row();
  for (const s of ['S', 'M', 'L', 'XL']) if (!known.has(s)) kb.text(`${s} (nuevo talle)`, `rsize:${productId}:${s}`).row();
  await ctx.reply('Que talle repone?', { reply_markup: kb });
});

bot.callbackQuery(/^rsize:(.+):(.+)$/, async (ctx) => {
  const [, productId, size] = ctx.match;
  await ctx.answerCallbackQuery();
  const kb = new InlineKeyboard();
  for (const n of [1, 5, 10, 20, 50]) kb.text(`+${n}`, `rqty:${productId}:${size}:${n}`);
  await ctx.reply('Cuantas unidades entraron?', { reply_markup: kb });
});

bot.callbackQuery(/^rqty:(.+):(.+):(\d+)$/, async (ctx) => {
  const [, productId, size, qtyStr] = ctx.match;
  const quantity = parseInt(qtyStr, 10);
  const res = await fetch(`${API}/products/${productId}/restock`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ size, quantity }),
  });
  const data = await res.json();
  await ctx.answerCallbackQuery({ text: 'Stock repuesto!' });
  await ctx.reply(`Listo! Sumadas ${quantity} unidades de talle ${size}. Stock nuevo de ese talle: ${data.variant.stockQuantity}. Total del producto: ${data.productStockQuantity}.`);
});

bot.command('baja', async (ctx) => {
  const code = (ctx.match as string || '').trim();
  if (!code) return ctx.reply('Uso: /baja CODIGO');
  const items = await (await fetch(`${API}/products`)).json();
  const product = items.find((p: any) => p.code === code);
  if (!product) return ctx.reply(`No encontre el producto con codigo ${code}.`);
  await fetch(`${API}/products/${product.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'inactive' }),
  });
  await ctx.reply(`${product.name} (${code}) dado de baja.`);
});

bot.command('aprobar', async (ctx) => {
  const items = await (await fetch(`${API}/content?status=pending_approval`)).json();
  if (!items.length) return ctx.reply('No hay contenido pendiente de aprobacion.');
  for (const c of items) {
    const kb = new InlineKeyboard().text('Aprobar', `capr:${c.id}`).text('Rechazar', `crej:${c.id}`);
    const info = `${c.channel} - ${c.contentType ?? 'post'}\n\n${c.caption ?? '(sin caption)'}\n\n${c.mediaUrl ? 'Media: ' + c.mediaUrl : ''}`;
    await ctx.reply(info, { reply_markup: kb });
  }
});

bot.callbackQuery(/^capr:(.+)$/, async (ctx) => {
  const id = ctx.match[1];
  const approver = ctx.from?.first_name || ctx.from?.username || 'operador';
  await fetch(`${API}/content/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'approved', approvedBy: approver }),
  });
  await ctx.answerCallbackQuery({ text: 'Aprobado!' });
  await ctx.editMessageText(`APROBADO por ${approver}`);
});

bot.callbackQuery(/^crej:(.+)$/, async (ctx) => {
  const id = ctx.match[1];
  const approver = ctx.from?.first_name || ctx.from?.username || 'operador';
  await fetch(`${API}/content/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'rejected', approvedBy: approver }),
  });
  await ctx.answerCallbackQuery({ text: 'Rechazado' });
  await ctx.editMessageText(`RECHAZADO por ${approver}`);
});

bot.start();
console.log('Agustina (bot Telegram) escuchando...');
