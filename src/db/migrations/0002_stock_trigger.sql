CREATE OR REPLACE FUNCTION decrement_stock_on_sale()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.product_variant_id IS NOT NULL THEN
    UPDATE product_variants
    SET stock_quantity = GREATEST(stock_quantity - NEW.quantity, 0)
    WHERE id = NEW.product_variant_id;

    UPDATE products p
    SET stock_quantity = (
      SELECT COALESCE(SUM(stock_quantity), 0) FROM product_variants WHERE product_id = p.id
    )
    WHERE p.id = (SELECT product_id FROM product_variants WHERE id = NEW.product_variant_id);
  ELSIF NEW.product_id IS NOT NULL THEN
    UPDATE products
    SET stock_quantity = GREATEST(stock_quantity - NEW.quantity, 0)
    WHERE id = NEW.product_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decrement_stock_on_sale ON order_items;
CREATE TRIGGER trg_decrement_stock_on_sale
AFTER INSERT ON order_items
FOR EACH ROW
EXECUTE FUNCTION decrement_stock_on_sale();
