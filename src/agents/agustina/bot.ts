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

bot.start();
console.log('Agustina (bot Telegram) escuchando...');
