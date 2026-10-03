"""Deterministic synthetic retail database used by the benchmark and the demo.

Seven related tables, including two with sensitive columns (``users.password_hash``,
``employees.ssn``) so access-control behaviour can be tested end to end. The same seed always
produces the same database, so benchmark results are reproducible.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

COUNTRIES = [("United States", 0.30), ("India", 0.22), ("United Kingdom", 0.12), ("Germany", 0.10), ("France", 0.08),
             ("Canada", 0.07), ("Australia", 0.06), ("Brazil", 0.05)]
SEGMENTS = ["Consumer", "Corporate", "Small Business"]
STATUSES = [("delivered", 0.72), ("shipped", 0.10), ("processing", 0.06), ("cancelled", 0.08), ("returned", 0.04)]
CATEGORIES = ["Electronics", "Books", "Home", "Clothing", "Sports", "Toys", "Grocery"]
PRODUCT_WORDS = {
    "Electronics": ["Headphones", "Keyboard", "Webcam", "Monitor", "Charger", "Speaker", "Router", "Mouse"],
    "Books": ["Novel", "Cookbook", "Atlas", "Biography", "Textbook", "Comic", "Dictionary", "Guide"],
    "Home": ["Lamp", "Cushion", "Kettle", "Blender", "Curtain", "Vase", "Mug", "Clock"],
    "Clothing": ["T-Shirt", "Jeans", "Jacket", "Scarf", "Hoodie", "Socks", "Cap", "Dress"],
    "Sports": ["Football", "Yoga Mat", "Dumbbell", "Racket", "Helmet", "Jersey", "Skipping Rope", "Bottle"],
    "Toys": ["Puzzle", "Lego Set", "Doll", "Board Game", "Robot", "Kite", "Cards", "Blocks"],
    "Grocery": ["Coffee", "Olive Oil", "Pasta", "Honey", "Tea", "Cereal", "Spice Mix", "Chocolate"],
}
FIRST = ["Aarav", "Emma", "Liam", "Sofia", "Noah", "Mia", "Lucas", "Ava", "Ethan", "Isha", "Oliver", "Chloe", "Arjun",
         "Hannah", "Mateo", "Zoe", "Kabir", "Lena", "Diego", "Nora", "Rohan", "Amelia", "Felix", "Priya", "Jack"]
LAST = ["Sharma", "Smith", "Mueller", "Silva", "Brown", "Patel", "Martin", "Johnson", "Dubois", "Singh", "Wilson",
        "Garcia", "Kumar", "Taylor", "Rossi", "Nguyen", "Khan", "Davies", "Lopez", "Anderson"]
DEPARTMENTS = ["Sales", "Engineering", "Support", "Finance", "Marketing"]

SCHEMA = """
CREATE TABLE customers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, country TEXT NOT NULL,
  segment TEXT NOT NULL, signup_date TEXT NOT NULL
);
CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(id),
  price REAL NOT NULL, stock INTEGER NOT NULL
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
  status TEXT NOT NULL, created_at TEXT NOT NULL, total REAL NOT NULL
);
CREATE TABLE order_items (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL, unit_price REAL NOT NULL
);
CREATE TABLE employees (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL, salary REAL NOT NULL,
  hire_date TEXT NOT NULL, manager_id INTEGER REFERENCES employees(id), ssn TEXT NOT NULL
);
CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
"""


def _pick(rng: random.Random, weighted: list[tuple[str, float]]) -> str:
    r, acc = rng.random(), 0.0
    for v, w in weighted:
        acc += w
        if r <= acc:
            return v
    return weighted[-1][0]


def build(path: str | Path, seed: int = 7, n_customers: int = 400, n_orders: int = 2500) -> Path:
    path = Path(path)
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)

    for i, c in enumerate(CATEGORIES, 1):
        con.execute("INSERT INTO categories VALUES (?,?)", (i, c))

    pid = 0
    for ci, cat in enumerate(CATEGORIES, 1):
        for w in PRODUCT_WORDS[cat]:
            pid += 1
            price = round(rng.uniform(4, 40) * (6 if cat == "Electronics" else 1) + 0.99, 2)
            con.execute("INSERT INTO products VALUES (?,?,?,?,?)", (pid, f"{w}", ci, price, rng.randint(0, 400)))
    n_products = pid

    start = date(2023, 1, 1)
    for cid in range(1, n_customers + 1):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.lower().replace(' ', '.')}{cid}@example.com"
        signup = start + timedelta(days=rng.randint(0, 540))
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)",
                    (cid, name, email, _pick(rng, COUNTRIES), rng.choice(SEGMENTS), signup.isoformat()))

    item_id = 0
    for oid in range(1, n_orders + 1):
        cid = rng.randint(1, n_customers)
        created = date(2023, 6, 1) + timedelta(days=rng.randint(0, 600))
        total = 0.0
        for _ in range(rng.choice([1, 1, 2, 2, 3, 4])):
            item_id += 1
            prod = rng.randint(1, n_products)
            price = con.execute("SELECT price FROM products WHERE id=?", (prod,)).fetchone()[0]
            qty = rng.choice([1, 1, 1, 2, 2, 3, 5])
            total += price * qty
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)", (item_id, oid, prod, qty, price))
        con.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                    (oid, cid, _pick(rng, STATUSES), created.isoformat(), round(total, 2)))

    for eid in range(1, 41):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        dept = rng.choice(DEPARTMENTS)
        hired = date(2015, 1, 1) + timedelta(days=rng.randint(0, 3000))
        mgr = None if eid <= 5 else rng.randint(1, 5)
        ssn = f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
        con.execute("INSERT INTO employees VALUES (?,?,?,?,?,?,?)",
                    (eid, name, dept, round(rng.uniform(40, 160) * 1000, 2), hired.isoformat(), mgr, ssn))

    for uid in range(1, 21):
        con.execute("INSERT INTO users VALUES (?,?,?,?)",
                    (uid, f"user{uid}@shop.example", "pbkdf2$" + "".join(rng.choices("0123456789abcdef", k=32)),
                     "admin" if uid <= 2 else "staff"))
    con.commit()
    con.close()
    return path


# Policy used by the benchmark and the demo: these columns can never be queried.
DENIED_COLUMNS = {"password_hash", "ssn"}
