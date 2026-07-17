# =============================================================================
#  models.py  —  Modelos de dados (tabelas do banco de dados)
# =============================================================================
#
#  Usamos SQLAlchemy como ORM (Object Relational Mapper).
#  Cada classe representa uma tabela no banco PostgreSQL.
# =============================================================================

from database import db
from datetime import datetime


class Store(db.Model):
    """
    Tabela: stores
    Representa uma loja/restaurante cadastrado no PDV.
    """
    __tablename__ = "stores"

    id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class StoreConfig(db.Model):
    """
    Tabela: store_config
    Configurações da loja — uma única linha (id=1).

    auto_accept:       Se True, aceita pedidos automaticamente sem intervenção manual.
    keeta_merchant_id: O ID que a Keeta atribuiu para esta loja.
    """
    __tablename__ = "store_config"

    id                = db.Column(db.Integer, primary_key=True)
    auto_accept       = db.Column(db.Boolean, default=True)
    keeta_merchant_id = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            "id":               self.id,
            "autoAccept":       self.auto_accept,
            "keetaMerchantId":  self.keeta_merchant_id,
        }


class MenuItem(db.Model):
    """
    Tabela: menu_items
    Itens do cardápio de uma loja.
    """
    __tablename__ = "menu_items"

    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    store_id = db.Column(db.Integer, nullable=False)
    name     = db.Column(db.String(255), nullable=False)
    price    = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id":      self.id,
            "storeId": self.store_id,
            "name":    self.name,
            "price":   self.price,
        }


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
    payment_type     = db.Column(db.String(50),  nullable=True)  # ONLINE ou NA_ENTREGA
    discount         = db.Column(db.Float,       nullable=True, default=0.0)

    # JSONs brutos salvos para auditoria/debug
    fees_json        = db.Column(db.Text,        nullable=True)
    discounts_json   = db.Column(db.Text,        nullable=True)

    created_at       = db.Column(db.String(100), nullable=True)

    # Relacionamento com os itens do pedido
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
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
            "paymentType":     self.payment_type,
            "discount":        self.discount,
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

    order = db.relationship("Order", back_populates="items")

    def to_dict(self):
        return {
            "id":           self.id,
            "menuItemId":   self.menu_item_id,
            "menuItemName": self.menu_item_name,
            "quantity":     self.quantity,
            "unitPrice":    self.unit_price,
            "originalPrice": self.original_price,
            "subtotal":     self.subtotal,
            "total":        self.total,
        }
