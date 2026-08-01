#!/usr/bin/env python3
# =============================================================================
#  seed_menu.py  —  Popula o banco de dados com um cardápio mock completo
# =============================================================================
#
#  Uso:
#    python seed_menu.py              → usa a store_id=1 (padrão)
#    python seed_menu.py --store 2    → usa a store_id=2
#    python seed_menu.py --reset      → limpa o cardápio existente antes
#
#  Este script cria:
#    - 2 categorias (Monte sua Massa, Bebidas)
#    - 7 itens (5 massas + 2 bebidas)
#    - 2 grupos de opções (Molhos com 4 opções, Proteínas com 3 opções)
#    - 7 regras de disponibilidade (uma por item)
#    - Vínculos: itens → categorias, itens → optionGroups, itens → availabilities
# =============================================================================

import os
import sys
import argparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configura a URL do banco (mesma lógica do database.py)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:eSmbNiHfoAqGDnnBJhOyaJzYcqqpuEIC@tokaido.proxy.rlwy.net:24002/railway")
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

print("=" * 60)
print("  SEED MENU — Populando banco com cardápio mock")
print("=" * 60)
print(f"  Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# =============================================================================
#  Importa os modelos (usando a mesma definição do models.py)
#  Como o script roda standalone, definimos os modelos inline para não
#  depender do Flask app context.
# =============================================================================

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, ForeignKey, Table
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# Tabelas de associação
menu_item_option_groups = Table(
    "menu_item_option_groups", Base.metadata,
    Column("menu_item_id", Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), primary_key=True),
    Column("option_group_id", Integer, ForeignKey("menu_option_groups.id", ondelete="CASCADE"), primary_key=True),
)

menu_item_availabilities = Table(
    "menu_item_availabilities", Base.metadata,
    Column("menu_item_id", Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), primary_key=True),
    Column("availability_id", Integer, ForeignKey("menu_availabilities.id", ondelete="CASCADE"), primary_key=True),
)

menu_category_availabilities = Table(
    "menu_category_availabilities", Base.metadata,
    Column("category_id", Integer, ForeignKey("menu_categories.id", ondelete="CASCADE"), primary_key=True),
    Column("availability_id", Integer, ForeignKey("menu_availabilities.id", ondelete="CASCADE"), primary_key=True),
)


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    store_id      = Column(Integer, nullable=False, index=True)
    name          = Column(String(150), nullable=False)
    description   = Column(String(500), default="")
    external_code = Column(String(100), nullable=False)
    index         = Column(Integer, default=0)
    status        = Column(String(20), default="AVAILABLE")
    items         = relationship("MenuItem", back_populates="category", cascade="all, delete-orphan")


class MenuItem(Base):
    __tablename__ = "menu_items"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    store_id       = Column(Integer, nullable=False, index=True)
    category_id    = Column(Integer, ForeignKey("menu_categories.id"), nullable=True)
    name           = Column(String(150), nullable=False)
    description    = Column(String(500), default="")
    external_code  = Column(String(100), nullable=False)
    price          = Column(Float, nullable=False)
    original_price = Column(Float)
    status         = Column(String(20), default="AVAILABLE")
    image_url      = Column(String(500))
    index          = Column(Integer, default=0)
    category       = relationship("MenuCategory", back_populates="items")
    option_groups  = relationship("MenuOptionGroup", secondary=menu_item_option_groups, lazy="dynamic")
    availabilities = relationship("MenuAvailability", secondary=menu_item_availabilities, lazy="dynamic")


class MenuOptionGroup(Base):
    __tablename__ = "menu_option_groups"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    store_id      = Column(Integer, nullable=False, index=True)
    name          = Column(String(150), nullable=False)
    description   = Column(String(500), default="")
    external_code = Column(String(100), nullable=False)
    index         = Column(Integer, default=0)
    status        = Column(String(20), default="AVAILABLE")
    min_permitted = Column(Integer, default=0)
    max_permitted = Column(Integer, default=1)
    price_method  = Column(String(10), default="SUM")
    options       = relationship("MenuOption", back_populates="option_group", cascade="all, delete-orphan", order_by="MenuOption.index")


class MenuOption(Base):
    __tablename__ = "menu_options"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    option_group_id = Column(Integer, ForeignKey("menu_option_groups.id", ondelete="CASCADE"), nullable=False)
    name            = Column(String(150), nullable=False)
    description     = Column(String(500), default="")
    external_code   = Column(String(100), nullable=False)
    index           = Column(Integer, default=0)
    status          = Column(String(20), default="AVAILABLE")
    price           = Column(Float, default=0.0)
    max_permitted   = Column(Integer)
    option_group    = relationship("MenuOptionGroup", back_populates="options")


class MenuAvailability(Base):
    __tablename__ = "menu_availabilities"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    store_id   = Column(Integer, nullable=False, index=True)
    name       = Column(String(150), nullable=False)
    start_date = Column(String(20))
    end_date   = Column(String(20))
    hours      = relationship("AvailabilityHour", back_populates="availability", cascade="all, delete-orphan")


class AvailabilityHour(Base):
    __tablename__ = "availability_hours"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    availability_id = Column(Integer, ForeignKey("menu_availabilities.id", ondelete="CASCADE"), nullable=False)
    day_of_week     = Column(String(10), nullable=False)
    start_time      = Column(String(15), nullable=False)
    end_time        = Column(String(15), nullable=False)
    availability    = relationship("MenuAvailability", back_populates="hours")


# =============================================================================
#  DADOS MOCK DO CARDÁPIO
# =============================================================================

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

CATEGORIES_DATA = [
    {
        "name": "Monte sua Massa",
        "description": "Escolha sua massa e personalize com molho e proteína",
        "external_code": "monte-sua-massa",
        "index": 0,
    },
    {
        "name": "Bebidas",
        "description": None,
        "external_code": "bebidas",
        "index": 1,
    },
]

ITEMS_DATA = [
    # ---- Massas (categoria 0) ----
    {
        "name": "Monte seu Penne",
        "description": "Penne de massa fresca artesanal. Escolha seu molho e proteína nos complementos.",
        "external_code": "5895",
        "price": 36.90,
        "image_url": "https://assets.menuintegrado.com/exemplo/penne.jpg",
        "cat_index": 0,
        "og_indices": [0, 1],  # Molhos + Proteínas
    },
    {
        "name": "Monte seu Tagliarini",
        "description": "Tagliarini de massa fresca artesanal. Escolha seu molho e proteína nos complementos.",
        "external_code": "9978",
        "price": 37.90,
        "image_url": "https://assets.menuintegrado.com/exemplo/tagliarini.jpg",
        "cat_index": 0,
        "og_indices": [0, 1],
    },
    {
        "name": "Monte seu Nhoque de Mandioquinha",
        "description": "Nhoque de mandioquinha de massa fresca. Textura macia que derrete na boca. Escolha seu molho.",
        "external_code": "7353",
        "price": 38.90,
        "image_url": "https://assets.menuintegrado.com/exemplo/nhoque.jpg",
        "cat_index": 0,
        "og_indices": [0, 1],
    },
    {
        "name": "Monte seu Conchiglione Recheado 4 Queijos",
        "description": "Conchiglione de massa fresca recheado com seleção de quatro queijos. Escolha seu molho.",
        "external_code": "4221",
        "price": 44.90,
        "image_url": "https://assets.menuintegrado.com/exemplo/conchiglione.jpg",
        "cat_index": 0,
        "og_indices": [0, 1],
    },
    {
        "name": "Fusili 350g - Escolha seu molho",
        "description": "Fusili de massa fresca. O formato espiral absorve perfeitamente o molho.",
        "external_code": "9224",
        "price": 31.90,
        "image_url": "https://assets.menuintegrado.com/exemplo/fusili.jpg",
        "cat_index": 0,
        "og_indices": [0],  # Só Molhos
    },
    # ---- Bebidas (categoria 1) ----
    {
        "name": "Coca-Cola Tradicional Lata 350ml",
        "description": "Coca-Cola tradicional - lata 350 ml",
        "external_code": "9186",
        "price": 8.70,
        "image_url": "https://assets.menuintegrado.com/exemplo/coca-cola.jpg",
        "cat_index": 1,
        "og_indices": [],
    },
    {
        "name": "Guaraná Antarctica Tradicional Lata 350ml",
        "description": "Guaraná Antarctica tradicional - lata 350 ml",
        "external_code": "3824",
        "price": 9.30,
        "image_url": "https://assets.menuintegrado.com/exemplo/guarana.jpg",
        "cat_index": 1,
        "og_indices": [],
    },
]

OPTION_GROUPS_DATA = [
    {
        "name": "Escolha o Molho",
        "description": "Selecione um molho para acompanhar sua massa",
        "external_code": "og-molhos-001",
        "min_permitted": 1,
        "max_permitted": 1,
        "price_method": "SUM",
        "options": [
            {"name": "Molho do Chef", "description": "Molho exclusivo da casa com manteiga, tomate, alho e lemon pepper", "external_code": "molho-chef", "price": 0.0},
            {"name": "Molho Bolonhesa Caseiro", "description": "Tradicional molho de tomate com carne bovina selecionada", "external_code": "molho-bolonhesa", "price": 0.0},
            {"name": "Molho ao Sugo", "description": "Clássico molho de tomate, leve e saboroso", "external_code": "molho-sugo", "price": 0.0},
            {"name": "Molho Branco Cremoso", "description": "Molho cremoso e aveludado com suavidade e muito sabor", "external_code": "molho-branco", "price": 0.0},
        ],
    },
    {
        "name": "Adicione uma Proteína",
        "description": "Opcional: adicione uma proteína à sua massa",
        "external_code": "og-proteinas-001",
        "min_permitted": 0,
        "max_permitted": 1,
        "price_method": "SUM",
        "options": [
            {"name": "Filé de Frango Grelhado", "description": "", "external_code": "1368", "price": 12.90},
            {"name": "Filé de Frango Empanado", "description": "", "external_code": "7573", "price": 14.90},
            {"name": "Medalhão de Filet Mignon", "description": "Medalhão de filet mignon grelhado ao ponto, envolto em bacon", "external_code": "1426", "price": 19.90},
        ],
    },
]


# =============================================================================
#  FUNÇÃO PRINCIPAL DE SEED
# =============================================================================

def seed(store_id: int = 1, reset: bool = False):
    print(f"\n  Store ID: {store_id}")
    print(f"  Reset:    {reset}")

    if reset:
        print("\n  [RESET] Removendo cardápio existente...")
        session.execute(menu_item_availabilities.delete())
        session.execute(menu_item_option_groups.delete())
        session.execute(menu_category_availabilities.delete())
        session.query(MenuOption).delete()
        session.query(MenuOptionGroup).delete()
        session.query(MenuItem).delete()
        session.query(MenuAvailability).delete()
        session.query(AvailabilityHour).delete()
        session.query(MenuCategory).delete()
        session.commit()
        print("  [RESET] Cardápio removido.")

    # --- 1. Cria Categorias ---
    print("\n  [1/6] Criando categorias...")
    categories = []
    for i, cat_data in enumerate(CATEGORIES_DATA):
        cat = MenuCategory(
            store_id=store_id,
            name=cat_data["name"],
            description=cat_data["description"] or "",
            external_code=cat_data["external_code"],
            index=cat_data["index"],
            status="AVAILABLE",
        )
        session.add(cat)
        categories.append(cat)
        print(f"         ✓ {cat.name}")
    session.flush()

    # --- 2. Cria OptionGroups + Options ---
    print("\n  [2/6] Criando grupos de opções...")
    option_groups = []
    for og_data in OPTION_GROUPS_DATA:
        og = MenuOptionGroup(
            store_id=store_id,
            name=og_data["name"],
            description=og_data["description"] or "",
            external_code=og_data["external_code"],
            min_permitted=og_data["min_permitted"],
            max_permitted=og_data["max_permitted"],
            price_method=og_data["price_method"],
            status="AVAILABLE",
        )
        for j, opt_data in enumerate(og_data["options"]):
            og.options.append(MenuOption(
                name=opt_data["name"],
                description=opt_data.get("description", ""),
                external_code=opt_data["external_code"],
                price=opt_data["price"],
                index=j,
                status="AVAILABLE",
            ))
        session.add(og)
        option_groups.append(og)
        print(f"         ✓ {og.name} ({len(og.options)} opções)")
    session.flush()

    # --- 3. Cria Itens ---
    print("\n  [3/6] Criando itens...")
    items = []
    for idx, item_data in enumerate(ITEMS_DATA):
        cat = categories[item_data["cat_index"]]
        item = MenuItem(
            store_id=store_id,
            category_id=cat.id,
            name=item_data["name"],
            description=item_data["description"],
            external_code=item_data["external_code"],
            price=item_data["price"],
            original_price=item_data["price"],
            image_url=item_data["image_url"],
            index=idx,
            status="AVAILABLE",
        )
        session.add(item)
        items.append(item)
        print(f"         ✓ {item.name} (R$ {item.price:.2f}) → {cat.name}")
    session.flush()

    # --- 4. Vincula OptionGroups aos Itens ---
    print("\n  [4/6] Vinculando grupos de opções aos itens...")
    for idx, item_data in enumerate(ITEMS_DATA):
        item = items[idx]
        for og_idx in item_data["og_indices"]:
            og = option_groups[og_idx]
            item.option_groups.append(og)
            print(f"         ✓ {item.name} ← {og.name}")
    session.flush()

    # --- 5. Cria Availabilities (uma por item, 00:00-23:59 todos os dias) ---
    print("\n  [5/6] Criando regras de disponibilidade...")
    availabilities_list = []
    for item in items:
        av = MenuAvailability(
            store_id=store_id,
            name=f"Disponível sempre - {item.name}",
            start_date=None,
            end_date=None,
        )
        for day in DAYS:
            av.hours.append(AvailabilityHour(
                day_of_week=day,
                start_time="00:00:00.000Z",
                end_time="23:59:59.000Z",
            ))
        session.add(av)
        availabilities_list.append(av)
    session.flush()

    # --- 6. Vincula Availabilities aos Itens ---
    print("\n  [6/6] Vinculando disponibilidades aos itens...")
    for item, av in zip(items, availabilities_list):
        item.availabilities.append(av)
        print(f"         ✓ {item.name} ← disponível 7 dias 00:00-23:59")

    # --- COMMIT FINAL ---
    session.commit()
    print("\n" + "=" * 60)
    print(f"  ✅ SCRIPT CONCLUÍDO!")
    print(f"     Store ID:       {store_id}")
    print(f"     Categorias:     {len(categories)}")
    print(f"     Itens:          {len(items)}")
    print(f"     Grupos Opções:  {len(option_groups)}")
    print(f"     Disponibilidades: {len(availabilities_list)}")
    print("=" * 60)


# =============================================================================
#  MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Popula o banco com cardápio mock")
    parser.add_argument("--store", type=int, default=1, help="Store ID (default: 1)")
    parser.add_argument("--reset", action="store_true", help="Remove cardápio existente antes de inserir")
    args = parser.parse_args()

    seed(store_id=args.store, reset=args.reset)
    session.close()
