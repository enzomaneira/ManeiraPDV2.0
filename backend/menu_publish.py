# =============================================================================
#  menu_publish.py  —  Publicação manual do cardápio (Keeta e iFood)
# =============================================================================
#
#  Editar o cardápio no PDV muda só o RASCUNHO. Cada plataforma recebe o
#  cardápio quando o restaurante clica em "Publicar".
#
#  Keeta: ela busca o cardápio quando quer (GET /api/keeta/menu), então
#  guardamos o cardápio publicado (snapshot) e servimos ele, com:
#    - dados da loja ao vivo (status, contato, horário);
#    - status ao vivo (esgotado/pausado vai na hora, sem publicar).
#  iFood: o PDV envia categoria por categoria e item por item pela Catalog API.
#
#  Pausas (Esgotado/Disponível, pausar categoria/complemento) continuam
#  imediatas nas duas plataformas.
# =============================================================================

import base64
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

import requests

import ifood_client
import keeta_client
import menu_platforms
from database import db
from models import MenuCategory, MenuItem, MenuOption, MenuOptionGroup, StoreConfig, menu_item_option_groups

MENU_KEYS = ("menus", "categories", "itemOffers", "items", "optionGroups", "availabilities")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -----------------------------------------------------------------------------
#  Keeta
# -----------------------------------------------------------------------------

def _keeta_live(store_id: int) -> tuple[dict, dict]:
    from routes.keeta_webhook import _build_menu_response
    merchant = _build_menu_response(store_id, "KEETA")
    return merchant, {key: merchant.get(key, []) for key in MENU_KEYS}


def _live_statuses(store_id: int) -> dict:
    """Status atuais do banco, no formato dos ids do cardápio da Keeta."""
    categories = MenuCategory.query.filter_by(store_id=store_id).all()
    paused_categories = {c.id for c in categories if (c.status or "AVAILABLE") != "AVAILABLE"}
    items = MenuItem.query.filter_by(store_id=store_id).all()
    item_status = {i.id: (i.status or "AVAILABLE") for i in items}
    statuses = {("categories", str(c.id)): c.status or "AVAILABLE" for c in categories}
    for item in items:
        statuses[("items", str(item.id))] = item_status[item.id]
        offer = "UNAVAILABLE" if item.category_id in paused_categories else item_status[item.id]
        statuses[("itemOffers", f"offer-{item.id}")] = offer
    for option in MenuOption.query.join(MenuOptionGroup).filter(MenuOptionGroup.store_id == store_id).all():
        status = option.status or "AVAILABLE"
        if item_status.get(option.item_id, "AVAILABLE") != "AVAILABLE":
            status = "UNAVAILABLE"
        statuses[("options", str(option.id))] = status
    return statuses


def _overlay_statuses(parts: dict, statuses: dict) -> dict:
    """Status ao vivo sobre o publicado. O que foi excluído do PDV depois da
    publicação fica UNAVAILABLE (não pode mais ser vendido)."""
    for key in ("categories", "itemOffers", "items"):
        for entity in parts.get(key, []):
            entity["status"] = statuses.get((key, str(entity.get("id"))), "UNAVAILABLE")
    for group in parts.get("optionGroups", []):
        for option in group.get("options", []):
            option["status"] = statuses.get(("options", str(option.get("id"))), "UNAVAILABLE")
    return parts


def published_keeta_merchant(store_id: int) -> dict:
    """O que a Keeta deve ver: cardápio publicado + dados da loja e status ao vivo.
    Sem publicação anterior, a primeira versão é o cardápio atual (nada muda
    para a Keeta depois da atualização do PDV)."""
    live, parts = _keeta_live(store_id)
    config = StoreConfig.query.get(store_id)
    if config is not None and not config.keeta_menu_snapshot_json:
        config.keeta_menu_snapshot_json = json.dumps(parts, ensure_ascii=False)
        config.keeta_published_hash = menu_platforms.menu_hash(parts)
        config.keeta_published_at = _now()
        db.session.commit()
    snapshot = json.loads(config.keeta_menu_snapshot_json) if config is not None and config.keeta_menu_snapshot_json else parts
    snapshot = _overlay_statuses(snapshot, _live_statuses(store_id))
    return {**{k: v for k, v in live.items() if k not in MENU_KEYS}, **snapshot}


def keeta_status(store_id: int) -> dict:
    config = StoreConfig.query.get(store_id)
    if config is not None and config.keeta_merchant_id and not config.keeta_menu_snapshot_json:
        published_keeta_merchant(store_id)  # 1ª versão = o que a Keeta já tem hoje
    _, parts = _keeta_live(store_id)
    published = bool(config and config.keeta_published_hash)
    return {"publishedAt": config.keeta_published_at if config else None,
            "pending": (not published) or menu_platforms.menu_hash(parts) != config.keeta_published_hash,
            "linked": bool(config and config.keeta_merchant_id)}


def publish_keeta(store_id: int) -> tuple[bool, str | None]:
    """Grava o rascunho atual como publicado e pede para a Keeta buscar."""
    config = StoreConfig.query.get(store_id)
    if not config or not config.keeta_merchant_id:
        return False, "Loja ainda não está conectada à Keeta."
    _, parts = _keeta_live(store_id)
    config.keeta_menu_snapshot_json = json.dumps(parts, ensure_ascii=False)
    config.keeta_published_hash = menu_platforms.menu_hash(parts)
    config.keeta_published_at = _now()
    db.session.commit()
    return keeta_client.force_menu_sync(str(config.keeta_merchant_id).strip(), published_keeta_merchant(store_id))


def push_keeta_status(store_id: int):
    """Pausa/reativação: a Keeta busca de novo e recebe o publicado com o status novo."""
    config = StoreConfig.query.get(store_id)
    if not config or not config.keeta_merchant_id:
        return
    try:
        ok, err = keeta_client.force_menu_sync(str(config.keeta_merchant_id).strip(), published_keeta_merchant(store_id))
        print(f"[MenuPublish][keeta-status] store_id={store_id} | sucesso={ok} | erro={err}")
    except Exception as e:
        print(f"[MenuPublish][keeta-status] ERRO store_id={store_id}: {type(e).__name__}: {e}")


# -----------------------------------------------------------------------------
#  iFood (Catalog API v2.0)
# -----------------------------------------------------------------------------
#  Ids do iFood precisam estar no formato UUID v4: geramos um UUID estável a
#  partir da loja e do id do PDV (sempre o mesmo para a mesma entidade).

def _ifood_id(store_id: int, kind: str, local_id) -> str:
    digest = uuid.uuid5(uuid.NAMESPACE_URL, f"maneirapdv:{store_id}:{kind}:{local_id}").bytes
    return str(uuid.UUID(bytes=digest, version=4))


def _load_map(config) -> dict:
    try:
        data = json.loads(config.ifood_catalog_map_json) if config and config.ifood_catalog_map_json else {}
    except (TypeError, ValueError):
        data = {}
    # Outra loja do iFood ligada (ex.: credenciais novas): ids antigos não valem mais
    merchant = (config.ifood_merchant_id or "") if config else ""
    if data.get("merchantId") and data["merchantId"] != merchant:
        data = {}
    data["merchantId"] = merchant
    data.setdefault("catalogId", None)  # catálogo DEFAULT da loja no iFood
    data.setdefault("categories", {})   # id da categoria do PDV -> {"id": id no iFood, "name": nome}
    data.setdefault("items", [])        # ids de item enviados na última publicação
    data.setdefault("images", {})       # url da foto -> imagePath no iFood
    data.setdefault("sent", {})         # id do item no iFood -> hash do que foi enviado (só reenvia o que mudou)
    return data


# Gunicorn derruba a requisição em 120 s: paramos antes e guardamos o progresso;
# clicar em "Publicar" de novo continua de onde parou.
# Pior caso de um produto: foto (4+10 s) + envio da foto e PUT (5+15 s cada) = 54 s.
PUBLISH_TIME_BUDGET = 55
PHOTO_TIME_BUDGET = 40


def build_ifood_items(store_id: int) -> list[dict]:
    """Um payload de PUT /items por produto visível no iFood (sem categoryId,
    que só existe depois de criar a categoria no iFood)."""
    config = StoreConfig.query.get(store_id)
    same = menu_platforms.same_menu(config)
    visible = lambda entity: menu_platforms.is_visible(entity, "IFOOD", same)
    categories = {c.id: c for c in MenuCategory.query.filter_by(store_id=store_id).all()}
    items = MenuItem.query.filter_by(store_id=store_id, is_option_item=False).order_by(MenuItem.index, MenuItem.id).all()
    item_by_id = {i.id: i for i in MenuItem.query.filter_by(store_id=store_id).all()}
    payloads = []
    for item in items:
        category = categories.get(item.category_id)
        if category is None or not visible(item) or not visible(category):
            continue
        value, original = menu_platforms.item_prices(item, "IFOOD", same)
        status = "AVAILABLE" if (item.status or "AVAILABLE") == "AVAILABLE" and (category.status or "AVAILABLE") == "AVAILABLE" else "UNAVAILABLE"
        price = {"value": value}
        if original > value:
            price["originalValue"] = original
        main_product = {"id": _ifood_id(store_id, "product", item.id), "name": item.name,
                        "description": item.description or "", "optionGroups": []}
        products, groups, options = [main_product], [], []
        product_ids = {main_product["id"]}
        group_ids = [gid for (gid,) in db.session.query(menu_item_option_groups.c.option_group_id)
                     .filter(menu_item_option_groups.c.menu_item_id == item.id).all()]
        for group in MenuOptionGroup.query.filter(MenuOptionGroup.id.in_(group_ids)).order_by(MenuOptionGroup.index).all() if group_ids else []:
            group_options = []
            for option in sorted(group.options, key=lambda o: (o.index or 0, o.id)):
                option_item = item_by_id.get(option.item_id)
                if option_item is None or not visible(option):
                    continue
                product_id = _ifood_id(store_id, "product", option_item.id)
                if product_id not in product_ids:
                    products.append({"id": product_id, "name": option_item.name, "description": option_item.description or ""})
                    product_ids.add(product_id)
                opt_status = "AVAILABLE" if (option.status or "AVAILABLE") == "AVAILABLE" and (option_item.status or "AVAILABLE") == "AVAILABLE" else "UNAVAILABLE"
                group_options.append({"id": _ifood_id(store_id, "option", option.id), "productId": product_id,
                                      "status": opt_status, "price": {"value": menu_platforms.option_price(option, "IFOOD", same)}})
            if not group_options:
                continue
            group_id = _ifood_id(store_id, "group", group.id)
            groups.append({"id": group_id, "name": group.name, "status": group.status or "AVAILABLE",
                           "optionGroupType": "INGREDIENTS", "optionIds": [o["id"] for o in group_options]})
            options.extend(group_options)
            minimum = min(group.min_permitted or 0, len(group_options))
            maximum = max(minimum, min(group.max_permitted or 1, sum(max(1, o.max_permitted or 1) for o in group.options)))
            main_product["optionGroups"].append({"id": group_id, "min": minimum, "max": maximum})
        payloads.append({
            "_local": {"categoryId": category.id, "categoryName": category.name, "imageUrl": item.image_url},
            "item": {"id": _ifood_id(store_id, "item", item.id), "type": "DEFAULT", "status": status,
                     "productId": main_product["id"],  # o iFood exige: qual produto este item vende
                     "price": price, "externalCode": item.external_code or str(item.id)},
            "products": products, "optionGroups": groups, "options": options,
        })
    return payloads


def ifood_status(store_id: int) -> dict:
    config = StoreConfig.query.get(store_id)
    payloads = build_ifood_items(store_id)
    published = bool(config and config.ifood_published_hash)
    return {"publishedAt": config.ifood_published_at if config else None,
            "pending": (not published) or menu_platforms.menu_hash(payloads) != config.ifood_published_hash,
            "linked": bool(config and config.ifood_merchant_id), "configured": ifood_client.is_configured()}


def _upload_image(merchant_id: str, url: str, cache: dict, session) -> str | None:
    """Foto do produto no iFood (baixa do nosso armazenamento e envia). Guarda o
    imagePath por URL: a mesma foto não é enviada duas vezes."""
    if not url:
        return None
    if url in cache:
        return cache[url]
    try:
        response = session.get(url, timeout=(4, 10))
        if response.status_code != 200 or len(response.content) > 5 * 1024 * 1024:
            print(f"[MenuPublish][ifood-image] foto não baixada | status_code={response.status_code}")
            return None
        kind = "png" if url.lower().endswith(".png") else "jpeg"
        data = f"data:image/{kind};base64,{base64.b64encode(response.content).decode()}"
        status, body = ifood_client._request("POST", f"/catalog/v2.0/merchants/{merchant_id}/image/upload", json_body={"image": data})
        path = body.get("imagePath") if status in (200, 201) and isinstance(body, dict) else None
        if path:
            cache[url] = path
        else:
            print(f"[MenuPublish][ifood-image] falha no envio da foto | status_code={status}")
        return path
    except Exception as e:
        print(f"[MenuPublish][ifood-image] ERRO: {type(e).__name__}")
        return None


def _ifood_error(status, body) -> str:
    """Resposta de erro do iFood em texto curto: "400: item.productId must be a UUID; …"."""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        details = [d.get("message") for d in error.get("details") or [] if isinstance(d, dict) and d.get("message")]
        return f"{status}: " + ("; ".join(details[:3]) if details else str(error.get("message") or error.get("code")))
    if isinstance(body, dict) and body.get("message"):
        return f"{status}: {body['message']}"
    return f"{status}: {str(body)[:160]}"


def _sent_hash(body: dict, image_url) -> str:
    raw = json.dumps({"body": body, "image": image_url or ""}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def publish_ifood(store_id: int) -> dict:
    """Envia o cardápio do iFood: cria as categorias que faltam e reenvia cada
    produto completo (PUT /items). Produtos que saíram do cardápio são pausados."""
    config = StoreConfig.query.get(store_id)
    if not config or not config.ifood_merchant_id:
        return {"ok": False, "error": "Ligue a loja do iFood nas Configurações primeiro."}
    if not ifood_client.is_configured():
        return {"ok": False, "error": "Credenciais do iFood ainda não configuradas no servidor."}
    started = time.monotonic()
    merchant = config.ifood_merchant_id
    mapping = _load_map(config)
    payloads = build_ifood_items(store_id)
    errors, sent, paused = [], 0, 0

    # Catálogo: as categorias ficam dentro do catálogo DEFAULT da loja
    if not mapping.get("catalogId"):
        status, catalogs = ifood_client._request("GET", f"/catalog/v2.0/merchants/{merchant}/catalogs")
        catalogs = catalogs if status == 200 and isinstance(catalogs, list) else []
        default = next((c for c in catalogs if "DEFAULT" in (c.get("context") or [])), catalogs[0] if catalogs else None)
        if not default:
            print(f"[MenuPublish][ifood] store_id={store_id} | catálogo não encontrado | status_code={status}")
            return {"ok": False, "error": f"Não encontrei o cardápio (catálogo) da loja no iFood (resposta {status})."}
        mapping["catalogId"] = default.get("catalogId") or default.get("id")
    catalog = mapping["catalogId"]

    # Categorias: cria no iFood a que ainda não existe e renomeia a que mudou de nome
    tried = set()
    for payload in payloads:
        local = payload["_local"]
        key = str(local["categoryId"])
        known = mapping["categories"].get(key)
        if key in tried or (known and known.get("name") == local["categoryName"]):
            continue
        tried.add(key)
        if known:
            status, body = ifood_client._request("PATCH", f"/catalog/v2.0/merchants/{merchant}/catalogs/{catalog}/categories/{known['id']}",
                                                 json_body={"name": local["categoryName"]})
            if status in (200, 201, 202, 204):
                known["name"] = local["categoryName"]
                continue
            if status != 404:  # 404: a categoria não existe mais lá, então cria de novo
                errors.append(f"Categoria \"{local['categoryName']}\": o iFood não aceitou o novo nome ({_ifood_error(status, body)})")
                continue
        status, body = ifood_client._request("POST", f"/catalog/v2.0/merchants/{merchant}/catalogs/{catalog}/categories",
                                             json_body={"name": local["categoryName"], "status": "AVAILABLE", "template": "DEFAULT"})
        if status in (200, 201) and isinstance(body, dict) and body.get("id"):
            mapping["categories"][key] = {"id": body["id"], "name": local["categoryName"]}
        else:
            errors.append(f"Categoria \"{local['categoryName']}\": o iFood respondeu {_ifood_error(status, body)}")

    # Itens: só envia o que mudou desde o último envio que deu certo
    new_item_ids, skipped, left = [], 0, 0
    session = requests.Session()
    for position, payload in enumerate(payloads):
        if time.monotonic() - started > PUBLISH_TIME_BUDGET:
            left = len(payloads) - position
            break
        local = payload["_local"]
        category = mapping["categories"].get(str(local["categoryId"]))
        if not category:
            continue
        body = {k: v for k, v in payload.items() if k != "_local"}
        body["item"] = {**body["item"], "categoryId": category["id"]}
        item_id = body["item"]["id"]
        digest = _sent_hash(body, local.get("imageUrl"))
        if mapping["sent"].get(item_id) == digest and item_id in mapping["items"]:
            skipped += 1
            new_item_ids.append(item_id)
            continue
        image, photo_ok = None, True
        if local.get("imageUrl"):
            if local["imageUrl"] in mapping["images"] or time.monotonic() - started <= PHOTO_TIME_BUDGET:
                image = _upload_image(merchant, local["imageUrl"], mapping["images"], session)
            photo_ok = bool(image)
        if image:
            body["products"][0] = {**body["products"][0], "imagePath": image}
        status, response = ifood_client._request("PUT", f"/catalog/v2.0/merchants/{merchant}/items", json_body=body)
        if status in (200, 201, 202, 204):
            sent += 1
            new_item_ids.append(item_id)
            # Sem a foto, fica marcado para reenviar (e tentar a foto) na próxima
            if photo_ok:
                mapping["sent"][item_id] = digest
            else:
                mapping["sent"].pop(item_id, None)
        else:
            errors.append(f"Produto \"{body['products'][0]['name']}\": o iFood respondeu {_ifood_error(status, response)}")
    session.close()
    if left:
        errors.insert(0, f"Faltaram {left} produto(s): o envio levou mais tempo que o permitido. "
                         "Clique em Publicar no iFood de novo para continuar de onde parou.")

    current_ids = {p["item"]["id"] for p in payloads}
    # Produtos que estavam no iFood e saíram do cardápio (ou da plataforma): pausa
    if not left:
        for old_id in sorted(set(mapping["items"]) - current_ids):
            if time.monotonic() - started > PUBLISH_TIME_BUDGET:
                left = 1
                errors.insert(0, "Faltou pausar produtos que saíram do cardápio: clique em Publicar no iFood de novo para terminar.")
                break
            status, _ = ifood_client._request("PATCH", f"/catalog/v2.0/merchants/{merchant}/items/status",
                                              json_body={"itemId": old_id, "status": "UNAVAILABLE"})
            if status in (200, 202, 204, 404):
                paused += status != 404  # 404: já não existe no iFood (ex.: categoria apagada)
                mapping["sent"].pop(old_id, None)
                mapping["items"] = [i for i in mapping["items"] if i != old_id]
        keep_old = set(mapping["items"]) if left else (current_ids & set(mapping["items"]))
        mapping["items"] = sorted(set(new_item_ids) | keep_old)
    else:
        mapping["items"] = sorted(set(new_item_ids) | set(mapping["items"]))

    # Categorias que saíram do cardápio do iFood (excluídas no PDV ou sem nenhum
    # produto no iFood): apaga lá também
    removed_categories = 0
    if not left:
        current_categories = {str(p["_local"]["categoryId"]) for p in payloads}
        for key, info in list(mapping["categories"].items()):
            if key in current_categories:
                continue
            status, body = ifood_client._request("DELETE", f"/catalog/v2.0/merchants/{merchant}/categories/{info['id']}")
            if status in (200, 202, 204, 404):
                removed_categories += status != 404
                del mapping["categories"][key]
            else:
                errors.append(f"Categoria \"{info.get('name')}\": o iFood não deixou apagar ({_ifood_error(status, body)})")

    config.ifood_catalog_map_json = json.dumps(mapping)
    if not errors:
        config.ifood_published_hash = menu_platforms.menu_hash(payloads)
        config.ifood_published_at = _now()
    db.session.commit()
    for error in errors[:5]:
        print(f"[MenuPublish][ifood] store_id={store_id} | {error}")
    print(f"[MenuPublish][ifood] store_id={store_id} | enviados={sent}/{len(payloads)} | sem_mudanca={skipped} | faltaram={left} "
          f"| pausados={paused} | categorias_apagadas={removed_categories} | erros={len(errors)} | {time.monotonic() - started:.1f}s")
    return {"ok": not errors, "sent": sent, "unchanged": skipped, "total": len(payloads), "paused": paused, "removedCategories": removed_categories, "left": left, "errors": errors[:5]}


def _both_available(*statuses) -> str:
    return "AVAILABLE" if all((status or "AVAILABLE") == "AVAILABLE" for status in statuses) else "UNAVAILABLE"


def _ifood_patch(merchant: str, kind: str, ifood_id: str, status: str) -> None:
    key = "itemId" if kind == "items" else "optionId"
    ifood_client._request("PATCH", f"/catalog/v2.0/merchants/{merchant}/{kind}/status", json_body={key: ifood_id, "status": status})


def push_ifood_status(store_id: int, entity) -> None:
    """Pausa/reativação imediata no iFood do que já foi publicado lá. Mesma
    regra da publicação: o produto só vende com ele E a categoria disponíveis;
    a opção, com ela E o item dela disponíveis."""
    config = StoreConfig.query.get(store_id)
    if not config or not config.ifood_merchant_id or not ifood_client.is_configured():
        return
    published = set(_load_map(config)["items"])
    merchant = config.ifood_merchant_id
    try:
        if isinstance(entity, MenuItem):
            if not entity.is_option_item:
                category = MenuCategory.query.get(entity.category_id) if entity.category_id else None
                item_id = _ifood_id(store_id, "item", entity.id)
                if item_id in published:
                    _ifood_patch(merchant, "items", item_id, _both_available(entity.status, category.status if category else None))
            # Item usado como complemento: a opção acompanha
            for option in MenuOption.query.filter_by(item_id=entity.id).all():
                _ifood_patch(merchant, "options", _ifood_id(store_id, "option", option.id), _both_available(option.status, entity.status))
        elif isinstance(entity, MenuCategory):
            for item in entity.items:
                item_id = _ifood_id(store_id, "item", item.id)
                if not item.is_option_item and item_id in published:
                    _ifood_patch(merchant, "items", item_id, _both_available(item.status, entity.status))
        elif isinstance(entity, MenuOption):
            option_item = MenuItem.query.get(entity.item_id) if entity.item_id else None
            _ifood_patch(merchant, "options", _ifood_id(store_id, "option", entity.id),
                         _both_available(entity.status, option_item.status if option_item else None))
    except Exception as e:
        print(f"[MenuPublish][ifood-status] ERRO store_id={store_id}: {type(e).__name__}: {e}")


def pause_ifood_deleted(store_id: int, item_ids=(), option_ids=(), category_ids=()) -> None:
    """Excluído no PDV: some na hora do iFood. Categoria é apagada lá (com os
    produtos dela); produto e complemento são pausados (saem de vez na próxima
    publicação)."""
    config = StoreConfig.query.get(store_id)
    if not config or not config.ifood_merchant_id or not ifood_client.is_configured():
        return
    mapping = _load_map(config)
    published = set(mapping["items"])
    merchant = config.ifood_merchant_id
    try:
        gone = set()
        for local_id in category_ids:
            info = mapping["categories"].get(str(local_id))
            if not info:
                continue
            status, _ = ifood_client._request("DELETE", f"/catalog/v2.0/merchants/{merchant}/categories/{info['id']}")
            if status in (200, 202, 204, 404):
                del mapping["categories"][str(local_id)]
                gone.update(_ifood_id(store_id, "item", i) for i in item_ids)
        for local_id in item_ids:
            item_id = _ifood_id(store_id, "item", local_id)
            if item_id in published and item_id not in gone:
                _ifood_patch(merchant, "items", item_id, "UNAVAILABLE")
        for local_id in option_ids:
            _ifood_patch(merchant, "options", _ifood_id(store_id, "option", local_id), "UNAVAILABLE")
        if gone or category_ids:
            mapping["items"] = [i for i in mapping["items"] if i not in gone]
            for item_id in gone:
                mapping["sent"].pop(item_id, None)
            config.ifood_catalog_map_json = json.dumps(mapping)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[MenuPublish][ifood-delete] ERRO store_id={store_id}: {type(e).__name__}: {e}")
