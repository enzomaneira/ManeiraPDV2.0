#!/usr/bin/env python3
# =============================================================================
#  import_menu.py  —  Reestrutura o cardápio de uma loja a partir de um payload
#                     Open Delivery / Keeta (Merchant ou merchantUpdate MERCHANT)
# =============================================================================
#
#  Uso (simulação: mostra o resultado e desfaz tudo no fim):
#    python import_menu.py --db "$DATABASE_URL" --store 1 --payload menu.json
#
#  Gravar de verdade (faz backup antes, numa única transação):
#    python import_menu.py --db "$DATABASE_URL" --store 1 --payload menu.json \
#        --apply --backup-dir ../backups
#
#  Regras:
#  - Itens repetidos no payload (mesmo código, ou mesmo nome sem código) viram
#    um único item. Ex.: a Coca vendida sozinha e a Coca do combo são o mesmo
#    item, então "Esgotado" nela também a tira do combo.
#  - Grupos de opções idênticos repetidos por produto viram um só grupo,
#    vinculado a todos esses produtos.
#  - Itens existentes são atualizados pelo código externo (mantêm o id e o
#    código que a Keeta já conhece). Itens novos sem código ganham um código
#    derivado do nome, então rodar de novo atualiza em vez de duplicar.
#  - Itens usados só como opção viram complementos (sem categoria).
#  - Itens e grupos da loja que não estão no payload são removidos.
#  - Não altera contatos/horário da loja nem dispara envio para a Keeta.
# =============================================================================

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import OrderedDict
from datetime import datetime

from flask import Flask
from sqlalchemy import text

from database import db
from models import (
    MenuAvailability, MenuCategory, MenuItem, MenuOption, MenuOptionGroup,
    menu_category_availabilities, menu_item_availabilities, menu_item_option_groups,
)

CODE_MAX_LENGTH = 100


def _plain(value: str) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text_value if not unicodedata.combining(ch)).lower().strip()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", _plain(value).upper()).strip("-")


def _price(price) -> tuple[float, float]:
    """(valor atual, valor original) de um objeto price do Open Delivery."""
    price = price or {}
    original = float(price.get("originalValue") if price.get("originalValue") is not None else price.get("value") or 0)
    value = float(price.get("value") if price.get("value") is not None else original)
    return value, max(original, value)


def _option_price(price) -> float:
    """Preço de uma opção: objeto price do Open Delivery ou número."""
    return _price(price)[0] if isinstance(price, dict) else float(price or 0)


def _image_url(item: dict) -> str | None:
    for image in item.get("images") or []:
        if isinstance(image, dict) and image.get("URL"):
            return image["URL"]
    image = item.get("image")
    return image.get("URL") if isinstance(image, dict) and image.get("URL") else None


def _merchant(payload: dict) -> dict:
    if "updatedObjects" in payload:
        return payload["updatedObjects"][0]
    return payload


# -----------------------------------------------------------------------------
#  1. Normaliza o payload num plano: categorias, produtos, complementos, grupos
# -----------------------------------------------------------------------------

def build_plan(payload: dict, image_overrides: dict) -> dict:
    merchant = _merchant(payload)
    items = {item["id"]: item for item in merchant.get("items") or []}
    offers = {offer["id"]: offer for offer in merchant.get("itemOffers") or []}
    groups = {group["id"]: group for group in merchant.get("optionGroups") or []}

    def item_key(item_id):
        item = items[item_id]
        return ("code", item["externalCode"].strip()) if (item.get("externalCode") or "").strip() else ("name", _plain(item["name"]))

    # Produtos: na ordem das categorias (index = posição dentro da categoria)
    products = OrderedDict()
    categories = []
    for category in sorted(merchant.get("categories") or [], key=lambda c: c.get("index", 0)):
        product_keys = []
        for position, offer_id in enumerate(category.get("itemOfferId") or []):
            offer = offers[offer_id]
            key = item_key(offer["itemId"])
            item = items[offer["itemId"]]
            value, original = _price(offer.get("price"))
            if key in products:
                raise ValueError(f"Produto {item['name']!r} aparece em mais de uma oferta; não suportado.")
            url = _image_url(item)
            products[key] = {
                "name": item["name"].strip(),
                "description": (item.get("description") or "").strip(),
                "code": (item.get("externalCode") or "").strip() or _slug(item["name"])[:CODE_MAX_LENGTH],
                "price": value,
                "original_price": original,
                "status": offer.get("status") or item.get("status") or "AVAILABLE",
                "image_url": image_overrides.get(url, url),
                "category": category["name"].strip(),
                "index": position,
                "group_ids": list(offer.get("optionGroupsId") or []),
                "keeta_codes_in_category": [],
            }
            product_keys.append(key)
        categories.append({
            "name": category["name"].strip(),
            "description": (category.get("description") or "").strip(),
            "index": len(categories),
            "status": category.get("status") or "AVAILABLE",
            "product_keys": product_keys,
        })

    # Grupos: copias idênticas (mesmo nome, limites e opções) viram um grupo
    distinct_groups = OrderedDict()
    for group in merchant.get("optionGroups") or []:
        options = tuple(
            (item_key(option["itemId"]), _option_price(option.get("price")),
             (option.get("name") or items[option["itemId"]]["name"]).strip())
            for option in sorted(group.get("options") or [], key=lambda o: o.get("index", 0))
        )
        signature = (group["name"].strip(), (group.get("description") or "").strip(),
                     int(group.get("minPermitted") or 0), int(group.get("maxPermitted") or 1), options)
        entry = distinct_groups.setdefault(signature, {"source_ids": [], "source_codes": []})
        entry["source_ids"].append(group["id"])
        entry["source_codes"].append(group.get("externalCode"))

    option_groups = []
    used_group_codes = set()
    for (name, description, minimum, maximum, options), entry in distinct_groups.items():
        code = os.path.commonprefix(entry["source_codes"]).rstrip("-_") if len(entry["source_codes"]) > 1 else entry["source_codes"][0]
        code = code or f"OG-{_slug(name)}"
        base, n = code, 2
        while code in used_group_codes:
            code, n = f"{base}-{n}", n + 1
        used_group_codes.add(code)
        option_groups.append({
            "name": name, "description": description, "min": minimum, "max": maximum, "code": code,
            "index": len(option_groups),
            "options": [{"key": key, "price": price, "name": option_name, "index": i} for i, (key, price, option_name) in enumerate(options)],
            "source_ids": entry["source_ids"],
        })
    group_by_source = {source: group["code"] for group in option_groups for source in group["source_ids"]}
    for product in products.values():
        product["groups"] = list(OrderedDict.fromkeys(group_by_source[g] for g in product.pop("group_ids")))

    # Complementos: itens usados por opções que não são vendidos como produto
    complements = OrderedDict()
    for group in option_groups:
        for option in group["options"]:
            key = option["key"]
            if key in products or key in complements:
                continue
            source = next(items[i] for i in items if item_key(i) == key)
            complements[key] = {
                "name": source["name"].strip(),
                "description": (source.get("description") or "").strip(),
                "code": (source.get("externalCode") or "").strip() or f"COMP-{_slug(source['name'])}"[:CODE_MAX_LENGTH],
                "price": option["price"],
                "status": source.get("status") or "AVAILABLE",
                "image_url": _image_url(source),
            }
    return {"categories": categories, "products": products, "complements": complements, "option_groups": option_groups}


# -----------------------------------------------------------------------------
#  2. Backup e aplicação no banco
# -----------------------------------------------------------------------------

def backup_store_menu(store_id: int) -> dict:
    """Todas as colunas das tabelas de cardápio da loja (o suficiente para restaurar)."""
    queries = {
        "menu_categories": "select * from menu_categories where store_id = :s",
        "menu_items": "select * from menu_items where store_id = :s",
        "menu_option_groups": "select * from menu_option_groups where store_id = :s",
        "menu_options": "select o.* from menu_options o join menu_option_groups g on g.id = o.option_group_id where g.store_id = :s",
        "menu_item_option_groups": "select l.* from menu_item_option_groups l join menu_items i on i.id = l.menu_item_id where i.store_id = :s",
        "menu_availabilities": "select * from menu_availabilities where store_id = :s",
        "availability_hours": "select h.* from availability_hours h join menu_availabilities a on a.id = h.availability_id where a.store_id = :s",
        "menu_item_availabilities": "select l.* from menu_item_availabilities l join menu_items i on i.id = l.menu_item_id where i.store_id = :s",
        "menu_category_availabilities": "select l.* from menu_category_availabilities l join menu_categories c on c.id = l.category_id where c.store_id = :s",
    }
    return {table: [dict(row._mapping) for row in db.session.execute(text(sql), {"s": store_id})] for table, sql in queries.items()}


def apply_plan(plan: dict, store_id: int) -> list[str]:
    log = []
    existing_items = {item.external_code: item for item in MenuItem.query.filter_by(store_id=store_id).all()}
    existing_categories = MenuCategory.query.filter_by(store_id=store_id).all()

    # Categorias: casa pela maioria dos produtos (códigos) e, se não der, pelo nome
    categories = {}
    used = set()
    for wanted in plan["categories"]:
        codes = {plan["products"][key]["code"] for key in wanted["product_keys"]}
        def score(category):
            return sum(1 for item in category.items if item.external_code in codes)
        candidates = [c for c in existing_categories if c.id not in used]
        match = max(candidates, key=score, default=None)
        if match is None or score(match) == 0:
            match = next((c for c in candidates if _plain(c.name) == _plain(wanted["name"])), None)
        if match is None:
            match = MenuCategory(store_id=store_id, external_code=f"cat-{_slug(wanted['name']).lower()}", name=wanted["name"])
            db.session.add(match)
            log.append(f"+ categoria {wanted['name']}")
        elif (match.name, match.description or "", match.index) != (wanted["name"], wanted["description"], wanted["index"]):
            log.append(f"~ categoria {match.name!r} -> {wanted['name']!r} (posição {wanted['index']})")
        match.name, match.description, match.index, match.status = wanted["name"], wanted["description"], wanted["index"], wanted["status"]
        used.add(match.id)
        categories[wanted["name"]] = match
    db.session.flush()

    def upsert_item(spec, *, category=None, is_option_item=False):
        item = existing_items.get(spec["code"])
        values = {
            "name": spec["name"], "description": spec["description"], "price": spec["price"],
            "original_price": spec.get("original_price", spec["price"]), "status": spec["status"],
            "image_url": spec.get("image_url"), "category_id": category.id if category else None,
            "index": spec.get("index", 0), "is_option_item": is_option_item,
        }
        if item is None:
            item = MenuItem(store_id=store_id, external_code=spec["code"], **values)
            db.session.add(item)
            log.append(f"+ {'complemento' if is_option_item else 'produto'} {spec['name']} (R$ {spec['price']:.2f}, código {spec['code']})")
        else:
            changes = [f"{k}: {getattr(item, k)!r} -> {v!r}" for k, v in values.items() if getattr(item, k) != v]
            if changes:
                log.append(f"~ {item.name} ({spec['code']}): " + "; ".join(changes))
            for key, value in values.items():
                setattr(item, key, value)
        return item

    items_by_key = {}
    for key, spec in plan["products"].items():
        items_by_key[key] = upsert_item(spec, category=categories[spec["category"]])
    for key, spec in plan["complements"].items():
        items_by_key[key] = upsert_item(spec, is_option_item=True)
    db.session.flush()

    # Grupos: os da loja que não estão no payload saem (com opções e vínculos)
    wanted_codes = {group["code"] for group in plan["option_groups"]}
    existing_groups = {g.external_code: g for g in MenuOptionGroup.query.filter_by(store_id=store_id).all()}
    for code, group in existing_groups.items():
        if code not in wanted_codes:
            db.session.execute(menu_item_option_groups.delete().where(menu_item_option_groups.c.option_group_id == group.id))
            db.session.delete(group)
            log.append(f"- grupo {group.name} ({code}, {len(group.options)} opções)")
    db.session.flush()

    groups_by_code = {}
    for spec in plan["option_groups"]:
        group = existing_groups.get(spec["code"]) if spec["code"] in wanted_codes else None
        if group is None:
            group = MenuOptionGroup(store_id=store_id, external_code=spec["code"], name=spec["name"])
            db.session.add(group)
            log.append(f"+ grupo {spec['name']} (mín {spec['min']}, máx {spec['max']}, {len(spec['options'])} opções)")
        group.name, group.description, group.index = spec["name"], spec["description"], spec["index"]
        group.min_permitted, group.max_permitted, group.status, group.price_method = spec["min"], spec["max"], "AVAILABLE", "SUM"
        db.session.flush()
        current = {option.external_code: option for option in group.options}
        keep = set()
        for option_spec in spec["options"]:
            item = items_by_key[option_spec["key"]]
            code = f"{spec['code']}-{_slug(item.name)}"[:CODE_MAX_LENGTH]
            option = current.get(code)
            if option is None:
                option = MenuOption(option_group_id=group.id, external_code=code)
                db.session.add(option)
            option.item_id, option.name, option.description = item.id, option_spec["name"], ""
            option.price, option.index, option.status = option_spec["price"], option_spec["index"], "AVAILABLE"
            keep.add(code)
        for code, option in current.items():
            if code not in keep:
                db.session.delete(option)
        groups_by_code[spec["code"]] = group
    db.session.flush()

    # Vínculos produto ↔ grupo: exatamente os do payload
    product_ids = [items_by_key[key].id for key in plan["products"]]
    db.session.execute(menu_item_option_groups.delete().where(menu_item_option_groups.c.menu_item_id.in_(product_ids)))
    for key, spec in plan["products"].items():
        for code in spec["groups"]:
            db.session.execute(menu_item_option_groups.insert().values(menu_item_id=items_by_key[key].id, option_group_id=groups_by_code[code].id))

    # Itens da loja fora do payload saem (depois que nada mais aponta para eles)
    keep_ids = {item.id for item in items_by_key.values()}
    for item in MenuItem.query.filter_by(store_id=store_id).all():
        if item.id not in keep_ids:
            db.session.execute(menu_item_option_groups.delete().where(menu_item_option_groups.c.menu_item_id == item.id))
            db.session.execute(menu_item_availabilities.delete().where(menu_item_availabilities.c.menu_item_id == item.id))
            MenuOption.query.filter_by(item_id=item.id).delete()
            db.session.delete(item)
            log.append(f"- {'complemento' if item.is_option_item else 'produto'} {item.name} ({item.external_code})")
    for category in existing_categories:
        if category.id not in used:
            if MenuItem.query.filter_by(category_id=category.id).count() == 0:
                db.session.execute(menu_category_availabilities.delete().where(menu_category_availabilities.c.category_id == category.id))
                db.session.delete(category)
                log.append(f"- categoria {category.name}")
    db.session.flush()
    return log


def main():
    parser = argparse.ArgumentParser(description="Reestrutura o cardápio de uma loja a partir de um payload Open Delivery")
    parser.add_argument("--db", required=True, help="URL do banco (postgresql://... ou sqlite:///...)")
    parser.add_argument("--store", type=int, required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--image-override", action="append", default=[], metavar="URL_ANTIGA=URL_NOVA")
    parser.add_argument("--apply", action="store_true", help="grava (sem isso, só simula e desfaz)")
    parser.add_argument("--backup-dir", help="pasta do backup JSON (obrigatória com --apply)")
    args = parser.parse_args()
    if args.apply and not args.backup_dir:
        parser.error("--apply exige --backup-dir")

    payload = json.load(open(args.payload, encoding="utf-8"))
    overrides = dict(pair.split("=", 1) for pair in args.image_override)
    plan = build_plan(payload, overrides)

    app = Flask(__name__)
    url = args.db.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    db.init_app(app)
    with app.app_context():
        backup = backup_store_menu(args.store)
        if args.apply:
            os.makedirs(args.backup_dir, exist_ok=True)
            path = os.path.join(args.backup_dir, f"cardapio_loja{args.store}_{datetime.now():%Y%m%d-%H%M%S}.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(backup, handle, ensure_ascii=False, indent=1, default=str)
            print(f"backup: {path}")
        try:
            for line in apply_plan(plan, args.store):
                print(line)
            if args.apply:
                db.session.commit()
                print("GRAVADO.")
            else:
                db.session.rollback()
                print("SIMULAÇÃO: nada foi gravado.")
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    sys.exit(main())
