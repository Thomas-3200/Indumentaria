import Fastify from 'fastify';
import 'dotenv/config';
import { eq } from 'drizzle-orm';
import { db } from '../db/client.js';
import { suppliers, products, productVariants, orders, orderItems } from '../db/schema.js';

const app = Fastify({ logger: true });

app.get('/health', async () => ({ status: 'ok' }));

// Proveedores
app.post('/suppliers', async (req) => {
  const b = req.body as any;
  const [row] = await db.insert(suppliers).values({
    name: b.name, contactName: b.contactName, phone: b.phone, email: b.email, notes: b.notes,
  }).returning();
  return row;
});
app.get('/suppliers', async () => db.select().from(suppliers));

// Productos
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
app.get('/products/:id/variants', async (req) => {
  const { id } = req.params as any;
  return db.select().from(productVariants).where(eq(productVariants.productId, id));
});

// Ventas — registrar acá dispara el trigger automatico de stock
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
