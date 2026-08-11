"""
Finance calculator para Stylo Fino.

Implementa el modelo financiero oficial documentado en:
  clients/stylo_fino_finance_model.md

Funciones principales:
  - calculate_net_profit(sale_data) → float
  - calculate_sale_split(sale_data, leo_split, tomi_split) → dict con todos los montos
  - calculate_profit_split_50_50(net_profit, leo_split, tomi_split) → dict
  - calculate_partnership_33_33_33(net_profit) → dict
  - validate_margin(sale_data) → "healthy" | "low_margin_review" | "negative_margin"
  - format_sale_summary_for_telegram(sale_data, split_result) → str (HTML)

Las funciones son puras (no escriben en Supabase). El caller decide qué hacer con el resultado.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# =====================================================
# Configuración por defecto
# =====================================================

# Reparto interno Stepflow team en Fase 1 (configurable)
DEFAULT_LEO_SPLIT = 0.50
DEFAULT_TOMI_SPLIT = 0.50

# Umbral para considerar margen "bajo" (% de gross)
LOW_MARGIN_THRESHOLD = 0.10   # < 10% de margen sobre gross → revisar

# Sale origins válidos (alineados con CHECK constraint en sales.sale_origin)
SALE_ORIGINS = (
    "LOCAL_DIRECTA_SIN_STEPFLOW",   # cliente vino al local sin que Stepflow lo originara → NO auto-liquidar
    "LOCAL_CON_ORIGEN_STEPFLOW",    # vino al local pero originado por canal Stepflow → 50/50 aplica
    "INSTAGRAM_DM",
    "FACEBOOK_MARKETPLACE",
    "FACEBOOK_GRUPO",
    "WHATSAPP_ESTADO",
    "WHATSAPP_REDIRECT",
    "PEDIDO_POR_ENCARGO",
    "REVISION_MANUAL",
)

# Origins que NUNCA se liquidan automáticamente — siempre needs_review
NON_AUTO_SETTLE_ORIGINS = (
    "LOCAL_DIRECTA_SIN_STEPFLOW",
    "REVISION_MANUAL",
)


# =====================================================
# Modelos
# =====================================================

@dataclass
class SaleData:
    """Inputs para calcular una venta."""
    gross_amount: float                              # lo que paga el cliente
    product_cost: float = 0.0                        # costo proveedor
    shipping_cost: float = 0.0                       # envío absorbido
    packaging_cost: float = 0.0                      # bolsa, sticker, etiqueta
    payment_fee: float = 0.0                         # comisión MP/débito/crédito
    discount_amount: float = 0.0                     # descuento aplicado
    refund_amount: float = 0.0                       # devolución parcial
    other_direct_costs: float = 0.0                  # otros (caso por caso)
    settlement_model: str = "PROFIT_SPLIT_50_50"     # PROFIT_SPLIT_50_50 | PARTNERSHIP_33_33_33 | CUSTOM_REVIEW
    stock_origin: str = "LUCAS_STOCK"                # LUCAS_STOCK | PROVEEDOR_ENCARGO | SOCIEDAD_STOCK
    sale_origin: Optional[str] = None                # ver SALE_ORIGINS
    product_name: Optional[str] = None
    sale_id: Optional[str] = None


@dataclass
class SplitResult:
    """Resultado del cálculo de reparto.

    REGLA OFICIAL (2026-05-15):
      1) Primero se devuelve el COSTO de la prenda a quien lo puso (cost_recovery).
      2) Después se reparte la GANANCIA NETA según settlement_model.
      3) `*_amount` = cost_recovery + profit_share (TOTAL que recibe esa persona).

    Ejemplo: Lucas compra a $45.000, vende a $65.000.
      net_profit = 20.000
      lucas_cost_recovery = 45.000
      lucas_profit_share = 10.000
      leo_profit_share = 5.000
      tomi_profit_share = 5.000
      → lucas_amount = 55.000 ; leo_amount = 5.000 ; tomi_amount = 5.000
    """
    net_profit: float                 # gross - product_cost - costos directos
    # Cost recovery (devolución del costo a quien lo puso)
    lucas_cost_recovery: float
    leo_cost_recovery: float
    tomi_cost_recovery: float
    # Profit share (reparto de la ganancia neta según settlement_model)
    lucas_profit_share: float
    leo_profit_share: float
    tomi_profit_share: float
    stepflow_team_profit_share: float  # leo_profit_share + tomi_profit_share (Fase 1)
    # Totales finales (cost_recovery + profit_share por persona)
    lucas_amount: float
    leo_amount: float
    tomi_amount: float
    stepflow_team_amount: float        # leo_amount + tomi_amount
    settlement_model: str
    margin_status: str                 # healthy | low_margin_review | negative_margin | approved_exception
    needs_review: bool
    review_reason: str = ""


# =====================================================
# Funciones de cálculo
# =====================================================

def calculate_net_profit(sale: SaleData) -> float:
    """
    Ganancia neta = gross - todos los costos directos.
    Puede ser negativa.
    """
    return round(
        sale.gross_amount
        - sale.product_cost
        - sale.shipping_cost
        - sale.packaging_cost
        - sale.payment_fee
        - sale.discount_amount
        - sale.refund_amount
        - sale.other_direct_costs,
        2
    )


def calculate_profit_split_50_50(
    net_profit: float,
    leo_split: float = DEFAULT_LEO_SPLIT,
    tomi_split: float = DEFAULT_TOMI_SPLIT,
) -> dict:
    """
    Reparto Fase 1: 50% Lucas / 50% Stepflow team — sobre GANANCIA NETA REPARTIBLE.
    NUNCA sobre el precio de venta. NUNCA sobre el gross.
    El costo de producto y costos directos ya están descontados en net_profit
    ANTES de llamar a esta función.

    Stepflow team se subdivide entre Leo y Tomi (default 50/50).
    """
    if abs((leo_split + tomi_split) - 1.0) > 0.01:
        raise ValueError(
            f"leo_split + tomi_split debe sumar 1.0 (got {leo_split + tomi_split})"
        )

    lucas_share = round(net_profit * 0.50, 2)
    stepflow_share = round(net_profit - lucas_share, 2)  # ajuste rounding
    leo_share = round(stepflow_share * leo_split, 2)
    tomi_share = round(stepflow_share - leo_share, 2)

    return {
        "lucas_profit_share": lucas_share,
        "stepflow_team_profit_share": stepflow_share,
        "leo_profit_share": leo_share,
        "tomi_profit_share": tomi_share,
    }


def calculate_partnership_33_33_33(net_profit: float) -> dict:
    """
    Reparto Fase 2: 33,33% / 33,33% / 33,33% sobre GANANCIA NETA REPARTIBLE.
    """
    third = round(net_profit / 3, 2)
    lucas_share = third
    leo_share = third
    tomi_share = round(net_profit - lucas_share - leo_share, 2)

    return {
        "lucas_profit_share": lucas_share,
        "stepflow_team_profit_share": round(leo_share + tomi_share, 2),
        "leo_profit_share": leo_share,
        "tomi_profit_share": tomi_share,
    }


def calculate_cost_recovery(sale: SaleData) -> dict:
    """
    Devuelve el costo de producto a quien lo puso ANTES de repartir ganancia.

    Reglas por stock_origin:
      - LUCAS_STOCK         → Lucas recupera 100% del product_cost
      - SOCIEDAD_STOCK      → 1/3 cada socio
      - PROVEEDOR_ENCARGO   → Lucas recupera 100% (es él quien adelanta al proveedor;
                              si fuera otro caso, marcar settlement_model=CUSTOM_REVIEW)

    NOTE: cost_recovery se aplica solo sobre product_cost.
    Los costos directos (shipping, packaging, fees, etc.) ya están descontados
    en net_profit y son absorbidos por la operación, no se "devuelven" a nadie.
    """
    pc = round(sale.product_cost, 2)
    if pc <= 0:
        return {"lucas": 0.0, "leo": 0.0, "tomi": 0.0}

    if sale.stock_origin == "LUCAS_STOCK":
        return {"lucas": pc, "leo": 0.0, "tomi": 0.0}
    if sale.stock_origin == "PROVEEDOR_ENCARGO":
        return {"lucas": pc, "leo": 0.0, "tomi": 0.0}
    if sale.stock_origin == "SOCIEDAD_STOCK":
        third = round(pc / 3, 2)
        return {"lucas": third, "leo": third, "tomi": round(pc - 2 * third, 2)}
    # default conservador
    return {"lucas": pc, "leo": 0.0, "tomi": 0.0}


def validate_margin(sale: SaleData, net_profit: float) -> tuple[str, bool, str]:
    """
    Devuelve (margin_status, needs_review, review_reason).

    Reglas:
    - net_profit < 0  → 'negative_margin', needs_review=True
    - net_profit / gross < 10% → 'low_margin_review', needs_review=True
    - settlement_model='CUSTOM_REVIEW' → needs_review=True
    - sino → 'healthy', needs_review=False
    """
    if sale.settlement_model == "CUSTOM_REVIEW":
        return "unknown", True, "settlement_model=CUSTOM_REVIEW exige revisión humana"

    if sale.gross_amount <= 0:
        return "unknown", True, "gross_amount es 0 o negativo"

    if net_profit <= 0:
        return "negative_margin", True, f"net_profit={net_profit:.2f} <= 0, no liquidar automático"

    margin_ratio = net_profit / sale.gross_amount
    if margin_ratio < LOW_MARGIN_THRESHOLD:
        return ("low_margin_review", True,
                f"margen {margin_ratio:.1%} < {LOW_MARGIN_THRESHOLD:.0%}, revisar")

    return "healthy", False, ""


def calculate_sale_split(
    sale: SaleData,
    leo_split: float = DEFAULT_LEO_SPLIT,
    tomi_split: float = DEFAULT_TOMI_SPLIT,
) -> SplitResult:
    """
    Función principal: toma una SaleData y devuelve SplitResult.
    """
    net = calculate_net_profit(sale)
    margin_status, needs_review, reason = validate_margin(sale, net)

    if sale.settlement_model == "PROFIT_SPLIT_50_50":
        profit = calculate_profit_split_50_50(net, leo_split, tomi_split)
    elif sale.settlement_model == "PARTNERSHIP_33_33_33":
        profit = calculate_partnership_33_33_33(net)
    elif sale.settlement_model == "CUSTOM_REVIEW":
        profit = {"lucas_profit_share": 0.0, "stepflow_team_profit_share": 0.0,
                  "leo_profit_share": 0.0, "tomi_profit_share": 0.0}
    else:
        raise ValueError(f"settlement_model desconocido: {sale.settlement_model}")

    # Cost recovery: devolver el costo a quien lo puso ANTES de repartir ganancia
    recovery = calculate_cost_recovery(sale)

    # Validación cruzada: si stock_origin=SOCIEDAD_STOCK pero settlement=50_50 → revisar
    if sale.stock_origin == "SOCIEDAD_STOCK" and sale.settlement_model != "PARTNERSHIP_33_33_33":
        needs_review = True
        reason = (reason + " | " if reason else "") + (
            "stock_origin=SOCIEDAD_STOCK pero settlement_model no es PARTNERSHIP_33_33_33"
        )
    if sale.stock_origin == "LUCAS_STOCK" and sale.settlement_model == "PARTNERSHIP_33_33_33":
        needs_review = True
        reason = (reason + " | " if reason else "") + (
            "stock_origin=LUCAS_STOCK pero settlement_model=PARTNERSHIP_33_33_33 (debería ser PROFIT_SPLIT_50_50)"
        )

    # Sale origin: ventas locales sin intervención de Stepflow no se auto-liquidan
    if sale.sale_origin in NON_AUTO_SETTLE_ORIGINS:
        needs_review = True
        reason = (reason + " | " if reason else "") + (
            f"sale_origin={sale.sale_origin} → no liquidar automáticamente, requiere revisión humana"
        )
    if sale.sale_origin is not None and sale.sale_origin not in SALE_ORIGINS:
        needs_review = True
        reason = (reason + " | " if reason else "") + (
            f"sale_origin desconocido: {sale.sale_origin} (debería estar en SALE_ORIGINS)"
        )

    lucas_total = round(recovery["lucas"] + profit["lucas_profit_share"], 2)
    leo_total = round(recovery["leo"] + profit["leo_profit_share"], 2)
    tomi_total = round(recovery["tomi"] + profit["tomi_profit_share"], 2)
    stepflow_total = round(leo_total + tomi_total, 2)

    return SplitResult(
        net_profit=net,
        lucas_cost_recovery=recovery["lucas"],
        leo_cost_recovery=recovery["leo"],
        tomi_cost_recovery=recovery["tomi"],
        lucas_profit_share=profit["lucas_profit_share"],
        leo_profit_share=profit["leo_profit_share"],
        tomi_profit_share=profit["tomi_profit_share"],
        stepflow_team_profit_share=profit["stepflow_team_profit_share"],
        lucas_amount=lucas_total,
        leo_amount=leo_total,
        tomi_amount=tomi_total,
        stepflow_team_amount=stepflow_total,
        settlement_model=sale.settlement_model,
        margin_status=margin_status,
        needs_review=needs_review,
        review_reason=reason,
    )


# =====================================================
# Formato para Telegram
# =====================================================

def _money(n: float) -> str:
    """Formatea número como pesos argentinos: $11.000,50"""
    if n is None:
        return "—"
    s = f"{n:,.2f}"
    # Convertir 11,000.50 → 11.000,50 (formato AR)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${s}"


def format_sale_summary_for_telegram(sale: SaleData, result: SplitResult) -> str:
    """
    Devuelve string HTML formateado para mandar via Telegram (parse_mode=HTML).
    """
    direct = (
        sale.shipping_cost + sale.packaging_cost + sale.payment_fee
        + sale.discount_amount + sale.refund_amount + sale.other_direct_costs
    )

    model_label = {
        "PROFIT_SPLIT_50_50": "50/50 ganancia neta (Fase 1)",
        "PARTNERSHIP_33_33_33": "33/33/33 sociedad (Fase 2)",
        "CUSTOM_REVIEW": "⚠ REVISIÓN MANUAL",
    }.get(sale.settlement_model, sale.settlement_model)

    lines = ["✅ <b>Venta registrada</b>", ""]
    if sale.product_name:
        lines.append(f"<b>Producto:</b> {sale.product_name}")
    lines += [
        f"<b>Venta:</b> {_money(sale.gross_amount)}",
        f"<b>Costo producto:</b> {_money(sale.product_cost)}",
        f"<b>Costos directos:</b> {_money(direct)}",
        f"<b>Ganancia neta repartible:</b> {_money(result.net_profit)}",
        "",
        f"<b>Modelo:</b> {model_label}",
        f"<b>Stock origin:</b> {sale.stock_origin}",
        "",
        "<b>Devolución de costo</b> (al que puso la plata):",
        f"  Lucas: {_money(result.lucas_cost_recovery)}",
        f"  Leo:   {_money(result.leo_cost_recovery)}",
        f"  Tomi:  {_money(result.tomi_cost_recovery)}",
        "",
        "<b>Reparto de ganancia neta:</b>",
        f"  Lucas: {_money(result.lucas_profit_share)}",
        f"  Leo:   {_money(result.leo_profit_share)}",
        f"  Tomi:  {_money(result.tomi_profit_share)}",
        "",
        "<b>TOTAL a recibir:</b>",
        f"  Lucas: {_money(result.lucas_amount)}",
        f"  Leo:   {_money(result.leo_amount)}",
        f"  Tomi:  {_money(result.tomi_amount)}",
        "",
    ]

    if result.needs_review:
        lines.append(f"⚠ <b>Revisión requerida:</b> {result.review_reason}")
        lines.append("Estado: <code>settlement_status=disputed</code>")
    else:
        lines.append("Estado: pendiente de liquidación")

    return "\n".join(lines)


# =====================================================
# CLI / smoke test
# =====================================================

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

    print("=== Test 0: EJEMPLO OFICIAL — Lucas $45k, vende $65k ===")
    sale0 = SaleData(
        gross_amount=65000, product_cost=45000,
        product_name="Conjunto (ejemplo oficial finance_model.md)",
        settlement_model="PROFIT_SPLIT_50_50",
        stock_origin="LUCAS_STOCK",
    )
    r0 = calculate_sale_split(sale0)
    print(format_sale_summary_for_telegram(sale0, r0))
    # Aserciones del ejemplo oficial
    assert r0.net_profit == 20000, f"net_profit esperado 20000, got {r0.net_profit}"
    assert r0.lucas_cost_recovery == 45000, f"cost_recovery esperado 45000, got {r0.lucas_cost_recovery}"
    assert r0.lucas_profit_share == 10000, f"lucas_profit esperado 10000, got {r0.lucas_profit_share}"
    assert r0.leo_profit_share == 5000, f"leo_profit esperado 5000, got {r0.leo_profit_share}"
    assert r0.tomi_profit_share == 5000, f"tomi_profit esperado 5000, got {r0.tomi_profit_share}"
    assert r0.lucas_amount == 55000, f"lucas_total esperado 55000, got {r0.lucas_amount}"
    assert r0.leo_amount == 5000, f"leo_total esperado 5000, got {r0.leo_amount}"
    assert r0.tomi_amount == 5000, f"tomi_total esperado 5000, got {r0.tomi_amount}"
    print("\n✅ ASSERTS OK — ejemplo oficial validado\n")

    print("=== Test 1: Venta normal Fase 1 ===")
    sale = SaleData(
        gross_amount=60000, product_cost=35000,
        shipping_cost=2500, packaging_cost=500,
        product_name="Chaleco Nike Negro",
        settlement_model="PROFIT_SPLIT_50_50",
        stock_origin="LUCAS_STOCK",
    )
    result = calculate_sale_split(sale)
    print(format_sale_summary_for_telegram(sale, result))
    print()

    print("=== Test 2: Venta con MP (3%) ===")
    sale2 = SaleData(
        gross_amount=60000, product_cost=35000,
        shipping_cost=2500, packaging_cost=500, payment_fee=1800,
        product_name="Conjunto AFA Adidas",
    )
    print(format_sale_summary_for_telegram(sale2, calculate_sale_split(sale2)))
    print()

    print("=== Test 3: Sociedad 33/33/33 ===")
    sale3 = SaleData(
        gross_amount=60000, product_cost=35000,
        shipping_cost=2500, packaging_cost=500,
        settlement_model="PARTNERSHIP_33_33_33",
        stock_origin="SOCIEDAD_STOCK",
        product_name="Campera Puma Verde",
    )
    print(format_sale_summary_for_telegram(sale3, calculate_sale_split(sale3)))
    print()

    print("=== Test 4: Margen NEGATIVO (alerta) ===")
    sale4 = SaleData(
        gross_amount=40000, product_cost=35000,
        shipping_cost=5000, packaging_cost=500, payment_fee=1200,
        product_name="Buzo TNF Negro",
    )
    print(format_sale_summary_for_telegram(sale4, calculate_sale_split(sale4)))
    print()

    print("=== Test 6: LOCAL_DIRECTA_SIN_STEPFLOW → no auto-liquidar ===")
    sale6 = SaleData(
        gross_amount=60000, product_cost=35000,
        sale_origin="LOCAL_DIRECTA_SIN_STEPFLOW",
        product_name="Walk-in cliente sin redes",
    )
    print(format_sale_summary_for_telegram(sale6, calculate_sale_split(sale6)))
    print()

    print("=== Test 7: INSTAGRAM_DM → liquidación normal ===")
    sale7 = SaleData(
        gross_amount=60000, product_cost=35000,
        sale_origin="INSTAGRAM_DM",
        product_name="Vino por DM IG",
    )
    print(format_sale_summary_for_telegram(sale7, calculate_sale_split(sale7)))
    print()

    print("=== Test 5: Inconsistencia stock vs settlement ===")
    sale5 = SaleData(
        gross_amount=60000, product_cost=35000,
        stock_origin="SOCIEDAD_STOCK",
        settlement_model="PROFIT_SPLIT_50_50",   # mal: debería ser PARTNERSHIP
        product_name="Test inconsistencia",
    )
    print(format_sale_summary_for_telegram(sale5, calculate_sale_split(sale5)))
