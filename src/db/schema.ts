import { pgTable, uuid, text, timestamp, integer, numeric, boolean } from 'drizzle-orm/pg-core';

export const suppliers = pgTable('suppliers', {
  id: uuid('id').defaultRandom().primaryKey(),
  name: text('name').notNull(),
  contactName: text('contact_name'),
  phone: text('phone'),
  email: text('email'),
  notes: text('notes'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const clients = pgTable('clients', {
  id: uuid('id').defaultRandom().primaryKey(),
  name: text('name'),
  phone: text('phone'),
  instagramHandle: text('instagram_handle'),
  sourceChannel: text('source_channel'),
  notes: text('notes'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const conversations = pgTable('conversations', {
  id: uuid('id').defaultRandom().primaryKey(),
  clientId: uuid('client_id').references(() => clients.id),
  channel: text('channel').notNull(),
  status: text('status').default('open'),
  lastMessageAt: timestamp('last_message_at', { withTimezone: true }),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const messages = pgTable('messages', {
  id: uuid('id').defaultRandom().primaryKey(),
  conversationId: uuid('conversation_id').references(() => conversations.id),
  direction: text('direction').notNull(),
  contentType: text('content_type').default('text'),
  content: text('content'),
  mediaUrl: text('media_url'),
  generatedByAgent: boolean('generated_by_agent').default(false),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const products = pgTable('products', {
  id: uuid('id').defaultRandom().primaryKey(),
  code: text('code').unique(),
  name: text('name').notNull(),
  category: text('category'),
  price: numeric('price', { precision: 10, scale: 2 }),
  supplierId: uuid('supplier_id').references(() => suppliers.id),
  stockQuantity: integer('stock_quantity').default(0),
  colors: text('colors').array(),
  photoUrls: text('photo_urls').array(),
  status: text('status').default('active'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const productVariants = pgTable('product_variants', {
  id: uuid('id').defaultRandom().primaryKey(),
  productId: uuid('product_id').references(() => products.id).notNull(),
  size: text('size').notNull(),
  stockQuantity: integer('stock_quantity').default(0),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const orders = pgTable('orders', {
  id: uuid('id').defaultRandom().primaryKey(),
  clientId: uuid('client_id').references(() => clients.id),
  channel: text('channel').default('in_person'),
  status: text('status').default('pending'),
  total: numeric('total', { precision: 10, scale: 2 }),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const orderItems = pgTable('order_items', {
  id: uuid('id').defaultRandom().primaryKey(),
  orderId: uuid('order_id').references(() => orders.id),
  productId: uuid('product_id').references(() => products.id),
  productVariantId: uuid('product_variant_id').references(() => productVariants.id),
  quantity: integer('quantity').notNull(),
  unitPrice: numeric('unit_price', { precision: 10, scale: 2 }),
});

export const contentCalendar = pgTable('content_calendar', {
  id: uuid('id').defaultRandom().primaryKey(),
  channel: text('channel').notNull(),
  contentType: text('content_type'),
  mediaUrl: text('media_url'),
  caption: text('caption'),
  status: text('status').default('draft'),
  scheduledAt: timestamp('scheduled_at', { withTimezone: true }),
  approvedBy: text('approved_by'),
  approvedAt: timestamp('approved_at', { withTimezone: true }),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const agentsLog = pgTable('agents_log', {
  id: uuid('id').defaultRandom().primaryKey(),
  agentName: text('agent_name').notNull(),
  action: text('action').notNull(),
  relatedEntityType: text('related_entity_type'),
  relatedEntityId: uuid('related_entity_id'),
  result: text('result'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});
