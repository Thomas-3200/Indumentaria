CREATE OR REPLACE FUNCTION log_income_on_sale()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO transactions (type, category, amount, description, related_order_id)
  VALUES ('income', 'venta', NEW.total, 'Venta - pedido ' || NEW.id, NEW.id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_income_on_sale ON orders;
CREATE TRIGGER trg_log_income_on_sale
AFTER INSERT ON orders
FOR EACH ROW
EXECUTE FUNCTION log_income_on_sale();
