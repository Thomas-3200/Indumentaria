import Fastify from 'fastify';
import 'dotenv/config';
import { eq, and } from 'drizzle-orm';
import { db } from '../db/client.js';
import { suppliers, products, productVariants, orders, orderItems, contentCalendar, clients, conversations, messages } from '../db/schema.js';

const app = Fastify({ logger: true });

const OPEN_PATHS = ['/health', '/dashboard'];
app.addHook('preHandler', async (req, reply) => {
  const path = req.url.split('?')[0];
  if (OPEN_PATHS.includes(path)) return;
  if (req.headers['x-api-key'] !== process.env.API_SECRET) {
    reply.code(401).send({ error: 'unauthorized' });
  }
});

app.get('/health', async () => ({ status: 'ok' }));

app.get('/dashboard', async (req, reply) => {
  reply.type('text/html').send(DASHBOARD_HTML);
});

app.post('/suppliers', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(suppliers).values({
    name: b.name, contactName: b.contactName, phone: b.phone, email: b.email, notes: b.notes,
  }).returning();
  return row;
});
app.get('/suppliers', async () => db.select().from(suppliers));

app.post('/products', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(products).values({
    code: b.code, name: b.name, category: b.category, price: b.price,
    supplierId: b.supplierId, colors: b.colors, photoUrls: b.photoUrls,
  }).returning();
  if (Array.isArray(b.variants)) {
    for (const v of b.variants) {
      await db.insert(productVariants).values({ productId: row.id, size: v.size, stockQuantity: v.stock ?? 0 });
    }
    const total = b.variants.reduce((s: number, v: any) => s + (v.stock ?? 0), 0);
    await db.update(products).set({ stockQuantity: total }).where(eq(products.id, row.id));
  }
  return row;
});
app.get('/products', async () => db.select().from(products));
app.get('/products/:id', async (req) => {
  const { id } = req.params as any;
  const [row] = await db.select().from(products).where(eq(products.id, id));
  return row;
});
app.get('/products/:id/variants', async (req) => {
  const { id } = req.params as any;
  return db.select().from(productVariants).where(eq(productVariants.productId, id));
});
app.patch('/products/:id', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const updates: any = {};
  for (const k of ['name', 'category', 'price', 'colors', 'photoUrls', 'status', 'supplierId']) if (b[k] !== undefined) updates[k] = b[k];
  const [row] = await db.update(products).set(updates).where(eq(products.id, id)).returning();
  return row;
});

async function resyncProductStock(productId: string) {
  const variants = await db.select().from(productVariants).where(eq(productVariants.productId, productId));
  const total = variants.reduce((s, v) => s + (v.stockQuantity ?? 0), 0);
  await db.update(products).set({ stockQuantity: total }).where(eq(products.id, productId));
  return total;
}

app.post('/products/:id/restock', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const existing = await db.select().from(productVariants)
    .where(and(eq(productVariants.productId, id), eq(productVariants.size, b.size)));
  let variant;
  if (existing.length) {
    const [row] = await db.update(productVariants)
      .set({ stockQuantity: (existing[0].stockQuantity ?? 0) + b.quantity })
      .where(eq(productVariants.id, existing[0].id)).returning();
    variant = row;
  } else {
    const [row] = await db.insert(productVariants).values({ productId: id, size: b.size, stockQuantity: b.quantity }).returning();
    variant = row;
  }
  const productStockQuantity = await resyncProductStock(id);
  return { variant, productStockQuantity };
});

app.patch('/product-variants/:id', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const [row] = await db.update(productVariants).set({ stockQuantity: b.stockQuantity }).where(eq(productVariants.id, id)).returning();
  const productStockQuantity = await resyncProductStock(row.productId);
  return { variant: row, productStockQuantity };
});

app.post('/orders', async (req) => {
  const b = req.body as any;
  const total = b.items.reduce((s: number, it: any) => s + it.quantity * it.unitPrice, 0);
  const [order] = await db.insert(orders).values({
    clientId: b.clientId ?? null, channel: b.channel ?? 'in_person', status: 'confirmed', total: String(total),
  }).returning();
  for (const it of b.items) {
    await db.insert(orderItems).values({
      orderId: order.id, productId: it.productId, productVariantId: it.productVariantId ?? null,
      quantity: it.quantity, unitPrice: String(it.unitPrice),
    });
  }
  return { order };
});
app.get('/orders', async () => db.select().from(orders));

app.post('/content', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(contentCalendar).values({
    channel: b.channel, contentType: b.contentType, mediaUrl: b.mediaUrl, caption: b.caption,
    status: b.status ?? 'pending_approval', scheduledAt: b.scheduledAt ?? null,
  }).returning();
  return row;
});
app.get('/content', async (req) => {
  const { status } = req.query as any;
  if (status) return db.select().from(contentCalendar).where(eq(contentCalendar.status, status));
  return db.select().from(contentCalendar);
});
app.patch('/content/:id', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const updates: any = {};
  for (const k of ['status', 'caption', 'mediaUrl', 'scheduledAt']) if (b[k] !== undefined) updates[k] = b[k];
  if (b.approvedBy !== undefined) { updates.approvedBy = b.approvedBy; updates.approvedAt = new Date(); }
  const [row] = await db.update(contentCalendar).set(updates).where(eq(contentCalendar.id, id)).returning();
  return row;
});

app.post('/clients', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(clients).values({
    name: b.name, phone: b.phone, instagramHandle: b.instagramHandle, sourceChannel: b.sourceChannel, notes: b.notes,
  }).returning();
  return row;
});
app.get('/clients', async () => db.select().from(clients));
app.get('/clients/:id', async (req) => {
  const { id } = req.params as any;
  const [row] = await db.select().from(clients).where(eq(clients.id, id));
  return row;
});
app.patch('/clients/:id', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const updates: any = {};
  for (const k of ['name', 'phone', 'instagramHandle', 'sourceChannel', 'notes']) if (b[k] !== undefined) updates[k] = b[k];
  const [row] = await db.update(clients).set(updates).where(eq(clients.id, id)).returning();
  return row;
});

app.post('/conversations', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(conversations).values({
    clientId: b.clientId, channel: b.channel, status: b.status ?? 'open', lastMessageAt: new Date(),
  }).returning();
  return row;
});
app.get('/conversations', async (req) => {
  const { clientId, status } = req.query as any;
  let rows = await db.select().from(conversations);
  if (clientId) rows = rows.filter((r) => r.clientId === clientId);
  if (status) rows = rows.filter((r) => r.status === status);
  return rows;
});
app.post('/conversations/:id/messages', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const [row] = await db.insert(messages).values({
    conversationId: id, direction: b.direction, contentType: b.contentType ?? 'text',
    content: b.content, mediaUrl: b.mediaUrl, generatedByAgent: b.generatedByAgent ?? false,
  }).returning();
  await db.update(conversations).set({ lastMessageAt: new Date(), status: b.status ?? 'open' }).where(eq(conversations.id, id));
  return row;
});
app.get('/conversations/:id/messages', async (req) => {
  const { id } = req.params as any;
  return db.select().from(messages).where(eq(messages.conversationId, id));
});

const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><title>Sistema Indumentaria</title>
<style>
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px;background:#f7f7f9;color:#1a1a1a;}
h1{font-size:22px;margin-bottom:4px;} .sub{color:#666;margin-bottom:24px;font-size:14px;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px;}
.card{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08);}
.card h2{font-size:14px;margin:0 0 8px;color:#666;font-weight:500;} .stat{font-size:28px;font-weight:600;}
table{width:100%;border-collapse:collapse;font-size:13px;} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;}
th{color:#888;font-weight:500;}
.badge{padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;}
.pending{background:#fff3cd;color:#856404;} .approved,.active{background:#d4edda;color:#155724;}
.rejected{background:#f8d7da;color:#721c24;} .inactive{background:#eee;color:#999;}
.low{color:#c0392b;font-weight:600;}
section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08);}
section h2{font-size:16px;margin-top:0;}
</style></head><body>
<h1>Sistema Indumentaria — Dashboard</h1>
<div class="sub" id="updated">Cargando...</div>
<div class="grid" id="stats"></div>
<section><h2>Productos y stock</h2><table id="products-table"><thead><tr><th>Codigo</th><th>Nombre</th><th>Stock</th><th>Precio</th><th>Estado</th></tr></thead><tbody></tbody></table></section>
<section><h2>Ultimas ventas</h2><table id="orders-table"><thead><tr><th>Fecha</th><th>Canal</th><th>Total</th><th>Estado</th></tr></thead><tbody></tbody></table></section>
<section><h2>Contenido</h2><table id="content-table"><thead><tr><th>Canal</th><th>Caption</th><th>Estado</th><th>Aprobo</th></tr></thead><tbody></tbody></table></section>
<section><h2>Clientes</h2><table id="clients-table"><thead><tr><th>Nombre</th><th>Contacto</th><th>Canal</th></tr></thead><tbody></tbody></table></section>
<script>
const key = new URLSearchParams(location.search).get('key') || '';
async function api(p){const r=await fetch(p,{headers:{'x-api-key':key}});if(!r.ok)throw new Error('No autorizado');return r.json();}
function badge(t,c){return '<span class="badge '+c+'">'+t+'</span>';}
async function load(){
  const [products,ordersData,content,clientsData]=await Promise.all([api('/products'),api('/orders'),api('/content'),api('/clients')]);
  document.getElementById('updated').textContent='Actualizado: '+new Date().toLocaleString('es-AR');
  const activeP=products.filter(p=>p.status==='active');
  const low=activeP.filter(p=>(p.stockQuantity??0)<=3).length;
  const pend=content.filter(c=>c.status==='pending_approval').length;
  document.getElementById('stats').innerHTML=
    '<div class="card"><h2>Productos activos</h2><div class="stat">'+activeP.length+'</div></div>'+
    '<div class="card"><h2>Stock bajo</h2><div class="stat '+(low?'low':'')+'">'+low+'</div></div>'+
    '<div class="card"><h2>Ventas</h2><div class="stat">'+ordersData.length+'</div></div>'+
    '<div class="card"><h2>Contenido pendiente</h2><div class="stat">'+pend+'</div></div>'+
    '<div class="card"><h2>Clientes</h2><div class="stat">'+clientsData.length+'</div></div>';
  document.querySelector('#products-table tbody').innerHTML=products.map(p=>
    '<tr><td>'+(p.code||'-')+'</td><td>'+p.name+'</td><td class="'+((p.stockQuantity??0)<=3?'low':'')+'">'+(p.stockQuantity??0)+'</td><td>'+(p.price?'\$'+Number(p.price).toLocaleString('es-AR'):'-')+'</td><td>'+badge(p.status,p.status)+'</td></tr>'
  ).join('')||'<tr><td colspan="5">Sin productos</td></tr>';
  document.querySelector('#orders-table tbody').innerHTML=ordersData.slice().reverse().slice(0,20).map(o=>
    '<tr><td>'+new Date(o.createdAt).toLocaleString('es-AR')+'</td><td>'+o.channel+'</td><td>\$'+Number(o.total).toLocaleString('es-AR')+'</td><td>'+badge(o.status,o.status)+'</td></tr>'
  ).join('')||'<tr><td colspan="4">Sin ventas</td></tr>';
  document.querySelector('#content-table tbody').innerHTML=content.slice().reverse().map(c=>
    '<tr><td>'+c.channel+'</td><td>'+(c.caption||'').slice(0,60)+'</td><td>'+badge(c.status,c.status==='pending_approval'?'pending':c.status)+'</td><td>'+(c.approvedBy||'-')+'</td></tr>'
  ).join('')||'<tr><td colspan="4">Sin contenido</td></tr>';
  document.querySelector('#clients-table tbody').innerHTML=clientsData.map(c=>
    '<tr><td>'+(c.name||'-')+'</td><td>'+(c.phone||c.instagramHandle||'-')+'</td><td>'+(c.sourceChannel||'-')+'</td></tr>'
  ).join('')||'<tr><td colspan="3">Sin clientes</td></tr>';
}
load().catch(e=>document.getElementById('updated').textContent='Error: '+e.message);
setInterval(load,15000);
</script></body></html>`;

const port = Number(process.env.PORT || 3000);
app.listen({ port, host: '0.0.0.0' }).then(() => console.log(`API en puerto ${port}`));
