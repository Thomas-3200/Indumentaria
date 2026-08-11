import Fastify from 'fastify';
import 'dotenv/config';
import { eq, and } from 'drizzle-orm';
import { db } from '../db/client.js';
import { suppliers, products, productVariants, orders, orderItems } from '../db/schema.js';

const app = Fastify({ logger: true });

app.get('/health', async () => ({ status: 'ok' }));

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

// Editar producto (nombre, precio, categoria, dar de baja, etc)
app.patch('/products/:id', async (req) => {
  const { id } = req.params as any;
  const b = req.body as any;
  const updates: any = {};
  for (const k of ['name', 'category', 'price', 'colors', 'photoUrls', 'status', 'supplierId']) {
    if (b[k] !== undefined) updates[k] = b[k];
  }
  const [row] = await db.update(products).set(updates).where(eq(products.id, id)).returning();
  return row;
});

async function resyncProductStock(productId: string) {
  const variants = await db.select().from(productVariants).where(eq(productVariants.productId, productId));
  const total = variants.reduce((s, v) => s + (v.stockQuantity ?? 0), 0);
  await db.update(products).set({ stockQuantity: total }).where(eq(products.id, productId));
  return total;
}

// Reponer stock (SUMA a lo que ya hay, crea el talle si no existia)
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
    const [row] = await db.insert(productVariants)
      .values({ productId: id, size: b.size, stockQuantity: b.quantity }).returning();
    variant = row;
  }
  const productStockQuantity = await resyncProductStock(id);
  return { variant, productStockQuantity };
});

// Correccion manual directa de una variante (para arreglar errores de carga)
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

const port = Number(process.env.PORT || 3000);
app.listen({ port, host: '127.0.0.1' }).then(() => console.log(`API en puerto ${port}`));
