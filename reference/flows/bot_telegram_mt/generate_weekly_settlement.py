"""
Genera la liquidación semanal de Stylo Fino.

Lee todas las ventas con settlement_status='pending' del período indicado,
calcula totales por persona y crea un registro en `settlements`.

Notifica el resumen via Telegram a Lucas, Leo y Tomi (si están configurados).

Uso:
    python flows/bot_telegram_mt/generate_weekly_settlement.py \
        --client stylo_fino --from 2026-05-11 --to 2026-05-17

    # Default (semana pasada Lun→Dom):
    python flows/bot_telegram_mt/generate_weekly_settlement.py

    # Dry-run (no escribe ni notifica):
    python flows/bot_telegram_mt/generate_weekly_settlement.py --dry-run
"""
from __future__ import annotations

import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Importar el calculator
sys.path.insert(0, str(Path(__file__).resolve().parent))
from finance_calculator import (
    SaleData, calculate_sale_split, _money,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
env = {}
for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

# Multi-tenant: detectar --client SLUG temprano (default stylo_fino para compat)
_CLIENT_SLUG_EARLY = "stylo_fino"
for _i, _arg in enumerate(sys.argv):
    if _arg == '--client' and _i + 1 < len(sys.argv):
        _CLIENT_SLUG_EARLY = sys.argv[_i + 1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_config import load_client_config
_cfg = load_client_config(_CLIENT_SLUG_EARLY)

SB_URL = _cfg.supabase_url
SVC = _cfg.supabase_service_role_key
H_R = {"apikey": SVC, "Authorization": f"Bearer {SVC}"}
H_W = {**H_R, "Content-Type": "application/json", "Prefer": "return=representation"}
TG_TOKEN = _cfg.tg_bot_token
LUCAS_ID = str(_cfg.tg_lead_user_id) if _cfg.tg_lead_user_id else None
LEO_ID = str(_cfg.tg_operator_user_id) if _cfg.tg_operator_user_id else None
CLIENT_UUID_FROM_CFG = _cfg.client_uuid  # se usa abajo en main() en vez del hardcoded
AR = timezone(timedelta(hours=-3))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--client", default="stylo_fino")
    p.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    p.add_argument("--to",   dest="date_to",   help="YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-notify", action="store_true",
                   help="No mandar notificación Telegram")
    return p.parse_args()


def default_period() -> tuple[date, date]:
    """Devuelve la semana pasada (Lun→Dom)."""
    today = datetime.now(AR).date()
    # Lunes=0 ... Domingo=6
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def get_pending_sales(client_id: str, period_start: date, period_end: date) -> list[dict]:
    """Trae ventas pending del período."""
    iso_start = datetime.combine(period_start, datetime.min.time()).replace(tzinfo=AR).isoformat()
    iso_end_exclusive = datetime.combine(period_end + timedelta(days=1), datetime.min.time()).replace(tzinfo=AR).isoformat()
    url = (f"{SB_URL}/rest/v1/sales"
           f"?client_id=eq.{client_id}"
           f"&sale_date=gte.{urllib.parse.quote(iso_start)}"
           f"&sale_date=lt.{urllib.parse.quote(iso_end_exclusive)}"
           f"&settlement_status=eq.pending"
           f"&payment_status=eq.paid"
           f"&delivery_status=eq.delivered"
           f"&select=*"
           f"&order=sale_date.asc")
    try:
        return json.loads(urllib.request.urlopen(
            urllib.request.Request(url, headers=H_R), timeout=15
        ).read())
    except urllib.error.HTTPError as e:
        print(f"  ERROR: {e.code} {e.read().decode()[:200]}")
        return []


def insert_settlement(client_id: str, period_start: date, period_end: date,
                      totals: dict, num_sales: int) -> Optional[str]:
    body = {
        "client_id": client_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_gross_sales": totals["gross"],
        "total_product_cost": totals["product_cost"],
        "total_direct_costs": totals["direct_costs"],
        "total_net_profit": totals["net_profit"],
        # Cost recovery (devolución de costo a quien lo puso)
        "total_lucas_cost_recovery": totals["lucas_cost_recovery"],
        "total_leo_cost_recovery": totals["leo_cost_recovery"],
        "total_tomi_cost_recovery": totals["tomi_cost_recovery"],
        # Profit share (reparto de ganancia neta)
        "total_lucas_profit_share": totals["lucas_profit_share"],
        "total_leo_profit_share": totals["leo_profit_share"],
        "total_tomi_profit_share": totals["tomi_profit_share"],
        # Totales finales (cost_recovery + profit_share)
        "total_lucas_amount": totals["lucas"],
        "total_stepflow_team_amount": totals["stepflow"],
        "total_leo_amount": totals["leo"],
        "total_tomi_amount": totals["tomi"],
        "num_sales": num_sales,
        "status": "draft",
    }
    req = urllib.request.Request(f"{SB_URL}/rest/v1/settlements",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers=H_W, method="POST")
    try:
        rows = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return rows[0]["id"] if rows else None
    except urllib.error.HTTPError as e:
        print(f"  ERROR insert settlement: {e.code} {e.read().decode()[:200]}")
        return None


def mark_sales_reviewed(sale_ids: list[str]):
    """Marca todas las ventas del settlement como reviewed."""
    if not sale_ids:
        return
    in_clause = "(" + ",".join(f'"{sid}"' for sid in sale_ids) + ")"
    url = f"{SB_URL}/rest/v1/sales?id=in.{urllib.parse.quote(in_clause)}"
    body = json.dumps({"settlement_status": "reviewed"}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={**H_W, "Prefer": "return=minimal"},
                                 method="PATCH")
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except urllib.error.HTTPError as e:
        print(f"  ERROR marking sales reviewed: {e.code}")


def tg_send(chat_id: str | int, text: str):
    if not TG_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, data=json.dumps(data).encode("utf-8"),
                                   headers={"Content-Type": "application/json"}),
            timeout=15
        ).read()
    except urllib.error.HTTPError as e:
        print(f"  ERROR tg_send: {e.code}")


def format_settlement_message(period_start: date, period_end: date,
                              totals: dict, num_sales: int, num_disputed: int) -> str:
    lines = [
        f"💰 <b>LIQUIDACIÓN SEMANAL — Stylo Fino</b>",
        f"<i>Período: {period_start.strftime('%d/%m')} → {period_end.strftime('%d/%m/%Y')}</i>",
        "",
        f"<b>Ventas procesadas:</b> {num_sales}",
    ]
    if num_disputed > 0:
        lines.append(f"⚠ <b>Ventas en revisión:</b> {num_disputed} (no incluidas)")
    lines += [
        "",
        f"<b>Facturación total:</b> {_money(totals['gross'])}",
        f"<b>Costo productos:</b> {_money(totals['product_cost'])}",
        f"<b>Costos directos:</b> {_money(totals['direct_costs'])}",
        f"<b>Ganancia neta repartible:</b> {_money(totals['net_profit'])}",
        "",
        f"<b>Devolución de costo:</b>",
        f"  Lucas:  {_money(totals['lucas_cost_recovery'])}",
        f"  Leo:    {_money(totals['leo_cost_recovery'])}",
        f"  Tomi:   {_money(totals['tomi_cost_recovery'])}",
        "",
        f"<b>Reparto de ganancia neta:</b>",
        f"  Lucas:  {_money(totals['lucas_profit_share'])}",
        f"  Leo:    {_money(totals['leo_profit_share'])}",
        f"  Tomi:   {_money(totals['tomi_profit_share'])}",
        "",
        f"<b>TOTAL a recibir:</b>",
        f"  Lucas:  {_money(totals['lucas'])}",
        f"  Leo:    {_money(totals['leo'])}",
        f"  Tomi:   {_money(totals['tomi'])}",
        "",
        "Status: <code>draft</code>",
        "Cuando todos confirmen → marcar approved → hacer transferencias.",
    ]
    return "\n".join(lines)


def main():
    args = parse_args()

    if args.date_from and args.date_to:
        period_start = datetime.strptime(args.date_from, "%Y-%m-%d").date()
        period_end = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    else:
        period_start, period_end = default_period()

    print(f"\n💰 Liquidación: {args.client}")
    print(f"   Período: {period_start} → {period_end}")
    print(f"   Modo: {'DRY-RUN' if args.dry_run else 'REAL'}\n")

    # Resuelto desde client_config.json (multi-tenant)
    CLIENT_UUID = CLIENT_UUID_FROM_CFG
    sales = get_pending_sales(CLIENT_UUID, period_start, period_end)

    if not sales:
        print("⚠ Sin ventas pendientes en el período.")
        return

    print(f"Ventas pendientes encontradas: {len(sales)}\n")

    # Calcular totales (verificar reparto vuelve a calcularse para validar consistency)
    totals = {"gross": 0.0, "product_cost": 0.0, "direct_costs": 0.0,
              "net_profit": 0.0,
              "lucas_cost_recovery": 0.0, "leo_cost_recovery": 0.0, "tomi_cost_recovery": 0.0,
              "lucas_profit_share": 0.0, "leo_profit_share": 0.0, "tomi_profit_share": 0.0,
              "lucas": 0.0, "stepflow": 0.0, "leo": 0.0, "tomi": 0.0}
    num_disputed = 0
    sale_ids_to_mark = []

    print(f"{'Fecha':<12} {'Producto':<35} {'Gross':>10} {'Net':>10} {'Lucas':>10} {'Leo':>10} {'Tomi':>10}")
    print("─" * 110)

    for s in sales:
        sale = SaleData(
            gross_amount=float(s.get("gross_amount") or 0),
            product_cost=float(s.get("product_cost") or 0),
            shipping_cost=float(s.get("shipping_cost") or 0),
            packaging_cost=float(s.get("packaging_cost") or 0),
            payment_fee=float(s.get("payment_fee") or 0),
            discount_amount=float(s.get("discount_amount") or 0),
            refund_amount=float(s.get("refund_amount") or 0),
            other_direct_costs=float(s.get("other_direct_costs") or 0),
            settlement_model=s.get("settlement_model", "PROFIT_SPLIT_50_50"),
            stock_origin=s.get("stock_origin", "LUCAS_STOCK"),
            product_name=s.get("product_name"),
        )
        result = calculate_sale_split(sale)

        if result.needs_review:
            num_disputed += 1
            print(f"⚠ {s.get('sale_date','')[:10]:<12} {(sale.product_name or '?')[:35]:<35}"
                  f" — DISPUTED ({result.review_reason[:40]})")
            continue

        totals["gross"] += sale.gross_amount
        totals["product_cost"] += sale.product_cost
        totals["direct_costs"] += (sale.shipping_cost + sale.packaging_cost
                                   + sale.payment_fee + sale.discount_amount
                                   + sale.refund_amount + sale.other_direct_costs)
        totals["net_profit"] += result.net_profit
        totals["lucas_cost_recovery"] += result.lucas_cost_recovery
        totals["leo_cost_recovery"] += result.leo_cost_recovery
        totals["tomi_cost_recovery"] += result.tomi_cost_recovery
        totals["lucas_profit_share"] += result.lucas_profit_share
        totals["leo_profit_share"] += result.leo_profit_share
        totals["tomi_profit_share"] += result.tomi_profit_share
        totals["lucas"] += result.lucas_amount
        totals["stepflow"] += result.stepflow_team_amount
        totals["leo"] += result.leo_amount
        totals["tomi"] += result.tomi_amount
        sale_ids_to_mark.append(s["id"])

        print(f"  {s.get('sale_date','')[:10]:<12} {(sale.product_name or '?')[:35]:<35}"
              f" {_money(sale.gross_amount):>10} {_money(result.net_profit):>10}"
              f" {_money(result.lucas_amount):>10} {_money(result.leo_amount):>10}"
              f" {_money(result.tomi_amount):>10}")

    # Round totals
    for k in totals: totals[k] = round(totals[k], 2)

    print("─" * 110)
    print(f"{'TOTAL':<48} {_money(totals['gross']):>10} {_money(totals['net_profit']):>10}"
          f" {_money(totals['lucas']):>10} {_money(totals['leo']):>10} {_money(totals['tomi']):>10}")
    if num_disputed > 0:
        print(f"\n⚠ {num_disputed} ventas en disputa, no incluidas en el reparto")

    if args.dry_run:
        print("\nDRY-RUN — no se insertó settlement ni se notificó")
        return

    # Insertar settlement
    settlement_id = insert_settlement(CLIENT_UUID, period_start, period_end,
                                      totals, len(sale_ids_to_mark))
    if settlement_id:
        print(f"\n✓ Settlement creado: {settlement_id} (status=draft)")
        mark_sales_reviewed(sale_ids_to_mark)
        print(f"✓ {len(sale_ids_to_mark)} ventas marcadas como reviewed")

    # Notificar
    if not args.no_notify:
        msg = format_settlement_message(period_start, period_end, totals,
                                        len(sale_ids_to_mark), num_disputed)
        for who, chat_id in [("Lucas", LUCAS_ID), ("Leo", LEO_ID)]:
            if chat_id:
                tg_send(chat_id, msg)
                print(f"  ✓ notificado a {who} ({chat_id})")


if __name__ == "__main__":
    main()
