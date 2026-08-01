# =============================================================================
#  models.py  —  Modelos de dados (tabelas do banco de dados)
# =============================================================================
#
#  Usamos SQLAlchemy como ORM (Object Relational Mapper).
#  Cada classe representa uma tabela no banco PostgreSQL.
# =============================================================================

from database import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

print("[Models][INIT] Módulo models.py carregado. Registrando classes User, Store, StoreConfig, MenuCategory, MenuItem, MenuAvailability, MenuOptionGroup, MenuOption, Order, OrderItem...")


class User(db.Model):
    """
    Tabela: users
    Representa um usuário (dono/operador) que faz login no sistema.

    Cada usuário está vinculado a NO MÁXIMO um restaurante (Store).
    Essa relação é 1 para 1: um usuário só administra a sua própria loja.
    """
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name          = db.Column(db.String(255), nullable=False)
    email         = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.String(100), nullable=True)

    # Relacionamento 1:1 com a loja (Store) desse usuário
    store = db.relationship("Store", back_populates="owner", uselist=False)

    def set_password(self, raw_password: str):
        print(f"[Models][User.set_password] INÍCIO | email={self.email} | password_len={len(raw_password)}")
        self.password_hash = generate_password_hash(raw_password)
        print(f"[Models][User.set_password] FIM | hash_preview={self.password_hash[:25]}...")

    def check_password(self, raw_password: str) -> bool:
        print(f"[Models][User.check_password] INÍCIO | email={self.email}")
        resultado = check_password_hash(self.password_hash, raw_password)
        print(f"[Models][User.check_password] FIM | resultado={resultado}")
        return resultado

    def to_dict(self):
        return {
            "id":      self.id,
            "name":    self.name,
            "email":   self.email,
            "storeId": self.store.id if self.store else None,
            "storeName": self.store.name if self.store else None,
        }


class Store(db.Model):
    """
    Tabela: stores
    Representa uma loja/restaurante cadastrado no PDV.

    Cada loja pertence a um único usuário (owner_id) — é o vínculo
    entre o login do sistema e o restaurante integrado com a Keeta.
    """
    __tablename__ = "stores"

    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name     = db.Column(db.String(255), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    owner = db.relationship("User", back_populates="store")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "ownerId": self.owner_id}


class StoreConfig(db.Model):
    """
    Tabela: store_config
    Configurações de integração da loja — uma linha por Store (store_id é a PK).

    auto_accept:         Se True, aceita pedidos automaticamente sem intervenção manual.
    keeta_merchant_id:   O ID que a Keeta atribuiu para esta loja.
    is_store_open:       Se a loja está aberta/fechada na Keeta.
    keeta_authorized:    Se o app está autorizado por este merchant na Keeta
                          (atualizado via webhook de autorização 1301/1302).
    keeta_auth_id:       Último authId recebido no webhook de autorização.
    """
    __tablename__ = "store_config"

    store_id          = db.Column(db.Integer, db.ForeignKey("stores.id"), primary_key=True)
    auto_accept       = db.Column(db.Boolean, default=True)
    keeta_merchant_id = db.Column(db.String(100), nullable=True)
    is_store_open     = db.Column(db.Boolean, default=True)
    keeta_authorized  = db.Column(db.Boolean, default=False)
    keeta_auth_id     = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "storeId":          self.store_id,
            "autoAccept":       self.auto_accept,
            "keetaMerchantId":  self.keeta_merchant_id,
            "isStoreOpen":      self.is_store_open,
            "keetaAuthorized":  self.keeta_authorized,
            "keetaAuthId":      self.keeta_auth_id,
        }


class MenuCategory(db.Model):
    """
    Tabela: menu_categories
    Categorias do cardápio (ex: "Pizzas", "Bebidas", "Sobremesas").
    Agrupa os itens (MenuItem) por categoria.
    Mapeia para a entidade `categories` do Open Delivery.
    """
    __tablename__ = "menu_categories"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    store_id      = db.Column(db.Integer, nullable=False, index=True)
    name          = db.Column(db.String(150), nullable=False)
    description   = db.Column(db.String(500), nullable=True, default="")
    external_code = db.Column(db.String(100), nullable=False)  # código externo (PDV Code)
    index         = db.Column(db.Integer, nullable=False, default=0)
    status        = db.Column(db.String(20), nullable=False, default="AVAILABLE")

    # Relacionamento com os itens
    items = db.relationship("MenuItem", back_populates="category", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":           self.id,
            "storeId":      self.store_id,
            "name":         self.name,
            "description":  self.description or "",
            "externalCode": self.external_code,
            "index":        self.index,
            "status":       self.status,
            "itemCount":    len(self.items) if self.items else 0,
            "items":        [i.to_dict() for i in self.items] if self.items else [],
        }


class MenuItem(db.Model):
    """
    Tabela: menu_items
    Itens do cardápio de uma loja.

    Mapeia para as entidades `items` + `itemOffers` do Open Delivery:
      - item:        id, name, description, externalCode, status
      - itemOffer:   id, price (value/originalValue), vinculado ao item
    """
    __tablename__ = "menu_items"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    store_id      = db.Column(db.Integer, nullable=False, index=True)
    category_id   = db.Column(db.Integer, db.ForeignKey("menu_categories.id"), nullable=True)
    name          = db.Column(db.String(150), nullable=False)
    description   = db.Column(db.String(500), nullable=True, default="")
    external_code = db.Column(db.String(100), nullable=False)  # código externo (PDV Code)
    price         = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, nullable=True)  # preço original (se houver desconto)
    status        = db.Column(db.String(20), nullable=False, default="AVAILABLE")
    image_url     = db.Column(db.String(500), nullable=True)
    index         = db.Column(db.Integer, nullable=False, default=0)

    category = db.relationship("MenuCategory", back_populates="items")

    def to_dict(self):
        return {
            "id":            self.id,
            "storeId":       self.store_id,
            "categoryId":    self.category_id,
            "categoryName":  self.category.name if self.category else None,
            "name":          self.name,
            "description":   self.description or "",
            "externalCode":  self.external_code,
            "price":         self.price,
            "originalPrice": self.original_price or self.price,
            "status":        self.status,
            "imageUrl":      self.image_url,
            "index":         self.index,
        }


# =============================================================================
#  TABELAS DE ASSOCIAÇÃO (many-to-many)
# =============================================================================

# Item ↔ OptionGroup (um item pode ter vários grupos de opções)
menu_item_option_groups = db.Table(
    "menu_item_option_groups",
    db.Column("menu_item_id", db.Integer, db.ForeignKey("menu_items.id", ondelete="CASCADE"), primary_key=True),
    db.Column("option_group_id", db.Integer, db.ForeignKey("menu_option_groups.id", ondelete="CASCADE"), primary_key=True),
)

# Item ↔ Availability (um item pode ter várias regras de disponibilidade)
menu_item_availabilities = db.Table(
    "menu_item_availabilities",
    db.Column("menu_item_id", db.Integer, db.ForeignKey("menu_items.id", ondelete="CASCADE"), primary_key=True),
    db.Column("availability_id", db.Integer, db.ForeignKey("menu_availabilities.id", ondelete="CASCADE"), primary_key=True),
)


# =============================================================================
#  OPTION GROUPS (grupos de opções / complementos / subitens)
# =============================================================================

class MenuOptionGroup(db.Model):
    """
    Tabela: menu_option_groups
    Grupos de opções para itens do cardápio.
    Ex: "Escolha o sabor da pizza", "Adicionais", "Tamanho"

    Mapeia para a entidade `optionGroups` do Open Delivery.
    """
    __tablename__ = "menu_option_groups"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    store_id      = db.Column(db.Integer, nullable=False, index=True)
    name          = db.Column(db.String(150), nullable=False)
    description   = db.Column(db.String(500), nullable=True, default="")
    external_code = db.Column(db.String(100), nullable=False)
    index         = db.Column(db.Integer, nullable=False, default=0)
    status        = db.Column(db.String(20), nullable=False, default="AVAILABLE")
    min_permitted = db.Column(db.Integer, nullable=False, default=0)   # mínimo de opções que devem ser escolhidas
    max_permitted = db.Column(db.Integer, nullable=False, default=1)   # máximo de opções que podem ser escolhidas
    price_method  = db.Column(db.String(10), nullable=False, default="SUM")  # SUM, HIGHEST, LOWEST

    # Opções dentro deste grupo
    options = db.relationship("MenuOption", back_populates="option_group",
                              cascade="all, delete-orphan", order_by="MenuOption.index")

    def to_dict(self):
        return {
            "id":            self.id,
            "storeId":       self.store_id,
            "name":          self.name,
            "description":   self.description or "",
            "externalCode":  self.external_code,
            "index":         self.index,
            "status":        self.status,
            "minPermitted":  self.min_permitted,
            "maxPermitted":  self.max_permitted,
            "priceMethod":   self.price_method,
            "optionCount":   len(self.options) if self.options else 0,
            "options":       [o.to_dict() for o in self.options] if self.options else [],
        }


class MenuOption(db.Model):
    """
    Tabela: menu_options
    Cada opção dentro de um OptionGroup.
    Ex: "Calabresa", "Margherita", "Frango com Catupiry"

    Mapeia para o array `options[]` dentro de `optionGroups` do Open Delivery.
    """
    __tablename__ = "menu_options"

    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    option_group_id = db.Column(db.Integer, db.ForeignKey("menu_option_groups.id", ondelete="CASCADE"), nullable=False)
    name            = db.Column(db.String(150), nullable=False)
    description     = db.Column(db.String(500), nullable=True, default="")
    external_code   = db.Column(db.String(100), nullable=False)
    index           = db.Column(db.Integer, nullable=False, default=0)
    status          = db.Column(db.String(20), nullable=False, default="AVAILABLE")
    price           = db.Column(db.Float, nullable=True, default=0.0)     # preço adicional desta opção
    max_permitted   = db.Column(db.Integer, nullable=True)                # limite de vezes que esta opção pode ser escolhida

    option_group = db.relationship("MenuOptionGroup", back_populates="options")

    def to_dict(self):
        return {
            "id":             self.id,
            "optionGroupId":  self.option_group_id,
            "name":           self.name,
            "description":    self.description or "",
            "externalCode":   self.external_code,
            "index":          self.index,
            "status":         self.status,
            "price":          self.price or 0.0,
            "maxPermitted":   self.max_permitted,
        }


# =============================================================================
#  AVAILABILITIES (disponibilidade por data/horário)
# =============================================================================

class MenuAvailability(db.Model):
    """
    Tabela: menu_availabilities
    Regras de disponibilidade para itens e categorias.
    Ex: "Disponível apenas de 01/05 a 30/05, Seg-Sex 11h-15h"

    Mapeia para a entidade `availabilities` do Open Delivery.
    """
    __tablename__ = "menu_availabilities"

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    store_id    = db.Column(db.Integer, nullable=False, index=True)
    name        = db.Column(db.String(150), nullable=False)          # nome descritivo
    start_date  = db.Column(db.String(20), nullable=True)            # YYYY-MM-DD (opcional)
    end_date    = db.Column(db.String(20), nullable=True)            # YYYY-MM-DD (opcional)

    hours = db.relationship("AvailabilityHour", back_populates="availability",
                            cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":         self.id,
            "storeId":    self.store_id,
            "name":       self.name,
            "startDate":  self.start_date,
            "endDate":    self.end_date,
            "hours":      [h.to_dict() for h in self.hours] if self.hours else [],
        }


class AvailabilityHour(db.Model):
    """
    Tabela: availability_hours
    Horários dentro de uma regra de disponibilidade.
    """
    __tablename__ = "availability_hours"

    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    availability_id = db.Column(db.Integer, db.ForeignKey("menu_availabilities.id", ondelete="CASCADE"), nullable=False)
    day_of_week     = db.Column(db.String(10), nullable=False)     # MONDAY, TUESDAY, etc.
    start_time      = db.Column(db.String(15), nullable=False)     # HH:MM:SS.000Z (UTC-0)
    end_time        = db.Column(db.String(15), nullable=False)     # HH:MM:SS.000Z (UTC-0)

    availability = db.relationship("MenuAvailability", back_populates="hours")

    def to_dict(self):
        return {
            "id":         self.id,
            "dayOfWeek":  self.day_of_week,
            "startTime":  self.start_time,
            "endTime":    self.end_time,
        }


# --- Atualiza MenuItem com relacionamentos para optionGroups e availabilities ---
MenuItem.option_groups = db.relationship(
    "MenuOptionGroup",
    secondary=menu_item_option_groups,
    backref=db.backref("menu_items", lazy="dynamic"),
    lazy="dynamic",
)

MenuItem.availabilities = db.relationship(
    "MenuAvailability",
    secondary=menu_item_availabilities,
    backref=db.backref("menu_items", lazy="dynamic"),
    lazy="dynamic",
)

# --- Atualiza MenuCategory com relacionamento para availabilities ---
menu_category_availabilities = db.Table(
    "menu_category_availabilities",
    db.Column("category_id", db.Integer, db.ForeignKey("menu_categories.id", ondelete="CASCADE"), primary_key=True),
    db.Column("availability_id", db.Integer, db.ForeignKey("menu_availabilities.id", ondelete="CASCADE"), primary_key=True),
)

MenuCategory.availabilities = db.relationship(
    "MenuAvailability",
    secondary=menu_category_availabilities,
    lazy="dynamic",
)


class Order(db.Model):
    """
    Tabela: orders
    Um pedido recebido — pode vir da Keeta (via webhook) ou ser criado manualmente (balcão).

    Campos de integração Keeta:
      external_id:  O ID único do pedido dentro da plataforma Keeta
      pickup_code:  Código de retirada exibido para o entregador
      display_id:   Número amigável exibido no app do cliente
    """
    __tablename__ = "orders"

    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    external_id      = db.Column(db.String(100), unique=True, nullable=True)  # ID da Keeta
    pickup_code      = db.Column(db.String(50),  nullable=True)
    display_id       = db.Column(db.String(50),  nullable=True)
    store_id         = db.Column(db.Integer,     nullable=False)

    # Status do pedido no PDV
    # Valores: NEW, PREPARING, READY_FOR_PICKUP, DELIVERY_IN_PROGRESS, COMPLETED, CANCELED
    status           = db.Column(db.String(50),  nullable=False, default="NEW")

    customer_name    = db.Column(db.String(255), nullable=True)
    delivery_address = db.Column(db.String(500), nullable=True)
    latitude         = db.Column(db.Float,       nullable=True)
    longitude        = db.Column(db.Float,       nullable=True)

    total_price      = db.Column(db.Float,       nullable=True)
    items_price      = db.Column(db.Float,       nullable=True)  # total.itemsPrice.value
    other_fees_total = db.Column(db.Float,       nullable=True)  # total.otherFees.value
    payment_type     = db.Column(db.String(50),  nullable=True)  # ONLINE ou NA_ENTREGA
    discount         = db.Column(db.Float,       nullable=True, default=0.0)

    # JSONs brutos salvos para auditoria/debug
    fees_json        = db.Column(db.Text,        nullable=True)
    discounts_json   = db.Column(db.Text,        nullable=True)

    created_at       = db.Column(db.String(100), nullable=True)

    # Relacionamento com os itens do pedido
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        import json as _json
        fees = []
        discounts = []
        if self.fees_json:
            try:
                fees = _json.loads(self.fees_json)
            except Exception:
                pass
        if self.discounts_json:
            try:
                discounts = _json.loads(self.discounts_json)
            except Exception:
                pass
        return {
            "id":              self.id,
            "externalId":      self.external_id,
            "pickupCode":      self.pickup_code,
            "displayId":       self.display_id,
            "storeId":         self.store_id,
            "status":          self.status,
            "customerName":    self.customer_name,
            "deliveryAddress": self.delivery_address,
            "latitude":        self.latitude,
            "longitude":       self.longitude,
            "totalPrice":      self.total_price,
            "itemsPrice":      self.items_price,
            "otherFeesTotal":  self.other_fees_total,
            "paymentType":     self.payment_type,
            "discount":        self.discount,
            "fees":            fees,
            "discounts":       discounts,
            "createdAt":       self.created_at,
            "items":           [item.to_dict() for item in self.items],
        }


class OrderItem(db.Model):
    """
    Tabela: order_items
    Cada linha representa um item dentro de um pedido.
    """
    __tablename__ = "order_items"

    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id       = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    menu_item_id   = db.Column(db.Integer, nullable=True)
    menu_item_name = db.Column(db.String(500), nullable=True)
    quantity       = db.Column(db.Integer,     nullable=False, default=1)
    unit_price     = db.Column(db.Float,       nullable=True)
    original_price = db.Column(db.Float,       nullable=True)
    subtotal       = db.Column(db.Float,       nullable=True)
    total          = db.Column(db.Float,       nullable=True)
    options_json   = db.Column(db.Text,        nullable=True)  # JSON com adicionais do item

    order = db.relationship("Order", back_populates="items")

    def to_dict(self):
        import json as _json
        options = []
        if self.options_json:
            try:
                options = _json.loads(self.options_json)
            except Exception:
                pass
        return {
            "id":           self.id,
            "menuItemId":   self.menu_item_id,
            "menuItemName": self.menu_item_name,
            "quantity":     self.quantity,
            "unitPrice":    self.unit_price,
            "originalPrice": self.original_price,
            "subtotal":     self.subtotal,
            "total":        self.total,
            "options":      options,
        }
