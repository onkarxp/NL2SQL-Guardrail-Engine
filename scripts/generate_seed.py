from faker import Faker
import random

fake = Faker()
random.seed(42)  # reproducible output

regions = ["North", "South", "East", "West"]
statuses = ["placed", "shipped", "cancelled", "returned"]
categories = ["Electronics", "Home", "Apparel", "Books", "Toys"]

lines = []

# Regions
for i, r in enumerate(regions, start=1):
    lines.append(f"INSERT INTO regions (id, name) VALUES ({i}, '{r}');")

# Customers
for i in range(1, 501):
    name = fake.name().replace("'", "''")
    email = fake.email()
    region_id = random.randint(1, 4)
    signup = fake.date_between(start_date="-2y", end_date="today")
    lines.append(
        f"INSERT INTO customers (id, name, email, region_id, signup_date) "
        f"VALUES ({i}, '{name}', '{email}', {region_id}, '{signup}');"
    )

# Products
for i in range(1, 51):
    name = fake.word().capitalize() + " " + fake.word().capitalize()
    category = random.choice(categories)
    price = round(random.uniform(5, 500), 2)
    lines.append(
        f"INSERT INTO products (id, name, category, unit_price) "
        f"VALUES ({i}, '{name}', '{category}', {price});"
    )

# Orders
for i in range(1, 2001):
    customer_id = random.randint(1, 500)
    region_id = random.randint(1, 4)
    status = random.choice(statuses)
    created = fake.date_time_between(start_date="-1y", end_date="now")
    lines.append(
        f"INSERT INTO orders (id, customer_id, region_id, status, created_at) "
        f"VALUES ({i}, {customer_id}, {region_id}, '{status}', '{created}');"
    )

# Order items
item_id = 1
for order_id in range(1, 2001):
    for _ in range(random.randint(1, 4)):
        product_id = random.randint(1, 50)
        quantity = random.randint(1, 5)
        amount = round(random.uniform(5, 500) * quantity, 2)
        lines.append(
            f"INSERT INTO order_items (id, order_id, product_id, quantity, amount) "
            f"VALUES ({item_id}, {order_id}, {product_id}, {quantity}, {amount});"
        )
        item_id += 1

with open("data/seed.sql", "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generated {len(lines)} INSERT statements into data/seed.sql")