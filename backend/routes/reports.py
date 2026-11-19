# =============================================================================
#  routes/reports.py  —  Relatórios de vendas
# =============================================================================
#
#  GET /api/reports?from=AAAA-MM-DD&to=AAAA-MM-DD&storeId=all|<id>
#
#  Junta os pedidos das lojas da conta (todas as marcas ou uma) no período,
#  em horário de Brasília, e devolve: números principais com comparação ao
#  período anterior, faturamento por dia (ou por hora), mapa de pico (dia da
#  semana × hora), itens e complementos mais vendidos, formas de pagamento,
#  tipo de entrega, faturamento por restaurante e clientes novos/recorrentes.
#
#  "Faturamento" = soma do total dos pedidos não cancelados.
# =============================================================================

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, g

from auth_utils import login_required
from models import Order

reports_bp = Blueprint("reports", __name__)

BRASILIA = timezone(timedelta(hours=-3))  # o Brasil não tem horário de verão desde 2019
MAX_RANGE_DAYS = 366
TOP_N = 10
WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
PAYMENT_LABELS = {
    "CREDIT": "Crédito", "DEBIT": "Débito", "CREDIT_DEBIT": "Cartão", "PIX": "PIX", "CASH": "Dinheiro",
    "MEAL_VOUCHER": "Vale-refeição", "FOOD_VOUCHER": "Vale-alimentação", "DIGITAL_WALLET": "Carteira digital",
    "COUPON": "Cupom", "REDEEM": "Resgate", "PREPAID_REDEEM": "Resgate", "OTHER": "Outro",
}


def _local_time(created_at) -> datetime | None:
    """createdAt da Keeta vem em UTC ("...Z"); pedidos antigos/manuais sem fuso
    foram gravados pelo servidor, que roda em UTC."""
    if not created_at:
        return None
    text = str(created_at).strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BRASILIA)


def _load(raw) -> dict:
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _base_item_name(item) -> str:
    """O nome salvo inclui complementos e observação: "X-Burguer (Bacon, Cheddar) [Obs: sem cebola]".
    Para somar o mesmo produto, volta ao nome do produto."""
    name = (item.menu_item_name or "Item").strip()
    if " [Obs: " in name:
        name = name[:name.index(" [Obs: ")].rstrip()
    try:
        options = json.loads(item.options_json) if item.options_json else []
    except (TypeError, ValueError):
        options = []
    from routes.orders import option_labels
    names = [str(o.get("name", "")) for o in options if isinstance(o, dict)]
    # Formato atual ("2x Bacon") e o antigo (só os nomes)
    for suffix in (f" ({', '.join(option_labels(options))})", f" ({', '.join(names)})"):
        if names and name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or "Item"


def _parse_day(value, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def _pct_change(current: float, previous: float):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _summarize(orders) -> dict:
    valid = [o for o in orders if o.status != "CANCELED"]
    canceled = [o for o in orders if o.status == "CANCELED"]
    revenue = sum(o.total_price or 0 for o in valid)
    return {
        "revenue": round(revenue, 2),
        "orders": len(valid),
        "averageTicket": round(revenue / len(valid), 2) if valid else 0,
        "canceled": len(canceled),
        "canceledValue": round(sum(o.total_price or 0 for o in canceled), 2),
        "cancelRate": round(len(canceled) / len(orders) * 100, 1) if orders else 0,
        "fees": round(sum(o.other_fees_total or 0 for o in valid), 2),
        "discounts": round(sum(abs(o.discount or 0) for o in valid), 2),
    }


@reports_bp.get("")
@reports_bp.get("/")
@login_required
def sales_report():
    today = datetime.now(BRASILIA).date()
    end = _parse_day(request.args.get("to"), today)
    start = _parse_day(request.args.get("from"), end - timedelta(days=29))
    if start > end:
        start, end = end, start
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        return jsonify({"error": f"Escolha um período de até {MAX_RANGE_DAYS} dias."}), 400

    stores = {store.id: store.name for store in g.current_user.stores}
    wanted = request.args.get("storeId", "all")
    if wanted not in ("", "all"):
        if not str(wanted).isdigit() or int(wanted) not in stores:
            return jsonify({"error": "Restaurante não encontrado."}), 404
        store_ids = [int(wanted)]
    else:
        store_ids = list(stores)

    days = (end - start).days + 1
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)

    # Filtra por data em Brasília (o created_at é texto, então filtramos em Python)
    current, previous = [], []
    for order in Order.query.filter(Order.store_id.in_(store_ids)).all() if store_ids else []:
        moment = _local_time(order.created_at)
        if not moment:
            continue
        day = moment.date()
        if start <= day <= end:
            current.append((order, moment))
        elif prev_start <= day <= prev_end:
            previous.append(order)

    orders = [o for o, _ in current]
    valid = [(o, m) for o, m in current if o.status != "CANCELED"]

    # Faturamento ao longo do tempo: por hora num dia só, senão por dia
    by_hour_mode = days == 1
    timeline = defaultdict(lambda: {"revenue": 0.0, "orders": 0})
    for order, moment in valid:
        key = moment.hour if by_hour_mode else moment.date().isoformat()
        timeline[key]["revenue"] += order.total_price or 0
        timeline[key]["orders"] += 1
    if by_hour_mode:
        series = [{"label": f"{h:02d}h", "key": h, **timeline[h]} for h in range(24)]
    else:
        series = []
        for i in range(days):
            day = start + timedelta(days=i)
            series.append({"label": day.strftime("%d/%m"), "key": day.isoformat(), "weekday": WEEKDAYS[day.weekday()], **timeline[day.isoformat()]})
    for point in series:
        point["revenue"] = round(point["revenue"], 2)

    # Mapa de pico: pedidos (não cancelados) por dia da semana × hora
    heat = [[0] * 24 for _ in range(7)]
    by_hour = [0] * 24
    for _, moment in valid:
        heat[moment.weekday()][moment.hour] += 1
        by_hour[moment.hour] += 1

    # Itens e complementos
    items = defaultdict(lambda: {"quantity": 0, "revenue": 0.0, "orders": 0})
    options = defaultdict(lambda: {"quantity": 0, "revenue": 0.0})
    for order, _ in valid:
        seen = set()
        for item in order.items:
            name = _base_item_name(item)
            qty = item.quantity or 0
            items[name]["quantity"] += qty
            items[name]["revenue"] += item.total or 0
            if name not in seen:
                items[name]["orders"] += 1
                seen.add(name)
            try:
                opts = json.loads(item.options_json) if item.options_json else []
            except (TypeError, ValueError):
                opts = []
            for opt in opts if isinstance(opts, list) else []:
                if not isinstance(opt, dict) or not opt.get("name"):
                    continue
                opt_qty = (opt.get("quantity") or 1) * qty
                options[opt["name"]]["quantity"] += opt_qty
                options[opt["name"]]["revenue"] += (opt.get("price") or 0) * opt_qty

    def top(table, key="quantity"):
        rows = sorted(({"name": n, **v} for n, v in table.items()), key=lambda r: (-r[key], -r["revenue"], r["name"]))
        for row in rows:
            row["revenue"] = round(row["revenue"], 2)
        return rows[:TOP_N], len(rows)

    top_items, item_count = top(items)
    top_options, option_count = top(options)

    # Formas de pagamento, tipo de entrega, restaurante, clientes
    payments = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    delivery = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    by_store = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    by_platform = defaultdict(lambda: {"orders": 0, "revenue": 0.0})
    customers = {"new": 0, "returning": 0, "unknown": 0}
    for order, _ in valid:
        value = order.total_price or 0
        methods = _load(order.payments_json).get("methods") or []
        method = methods[0].get("method") if methods and isinstance(methods[0], dict) else None
        if len(methods) > 1:
            label = "Mais de uma forma"
        elif method:
            label = PAYMENT_LABELS.get(method, "Outro")
        else:
            label = "Pago online" if order.payment_type == "ONLINE" else "Na entrega" if order.payment_type == "NA_ENTREGA" else "Balcão"
        payments[label]["orders"] += 1
        payments[label]["revenue"] += value

        by = _load(order.delivery_json).get("deliveredBy")
        platform_name = {"IFOOD": "iFood", "BALCAO": "Balcão"}.get(order.platform or "", "Keeta")
        kind = "Entrega própria" if by == "MERCHANT" else f"Entrega {platform_name}" if by == "MARKETPLACE" else "Não informado"
        by_platform[platform_name]["orders"] += 1
        by_platform[platform_name]["revenue"] += value
        delivery[kind]["orders"] += 1
        delivery[kind]["revenue"] += value

        by_store[stores.get(order.store_id, "Restaurante")]["orders"] += 1
        by_store[stores.get(order.store_id, "Restaurante")]["revenue"] += value

        count = _load(order.customer_json).get("ordersCount")
        if isinstance(count, (int, float)):
            customers["new" if count <= 1 else "returning"] += 1
        else:
            customers["unknown"] += 1

    def split(table):
        rows = sorted(({"name": n, "orders": v["orders"], "revenue": round(v["revenue"], 2)} for n, v in table.items()),
                      key=lambda r: (-r["revenue"], r["name"]))
        return rows

    summary = _summarize(orders)
    prev = _summarize(previous)
    summary["previous"] = prev
    summary["change"] = {key: _pct_change(summary[key], prev[key]) for key in ("revenue", "orders", "averageTicket", "canceled")}
    summary["itemsSold"] = sum(v["quantity"] for v in items.values())
    peak_hour = max(range(24), key=lambda h: by_hour[h]) if any(by_hour) else None
    best_day = max(series, key=lambda p: p["revenue"]) if series and any(p["revenue"] for p in series) else None

    return jsonify({
        "range": {"from": start.isoformat(), "to": end.isoformat(), "days": days,
                  "previousFrom": prev_start.isoformat(), "previousTo": prev_end.isoformat()},
        "stores": [{"id": sid, "name": name} for sid, name in stores.items()],
        "storeId": store_ids[0] if len(store_ids) == 1 and wanted not in ("", "all") else "all",
        "summary": summary,
        "timeline": {"unit": "hour" if by_hour_mode else "day", "points": series},
        "heatmap": {"weekdays": WEEKDAYS, "counts": heat},
        "byHour": by_hour,
        "peakHour": peak_hour,
        "bestDay": best_day,
        "topItems": top_items, "itemCount": item_count,
        "topOptions": top_options, "optionCount": option_count,
        "payments": split(payments),
        "delivery": split(delivery),
        "byStore": split(by_store),
        "byPlatform": split(by_platform),
        "customers": customers,
    })
