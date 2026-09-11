CATEGORICAL_COLUMNS = {
    "orders": ["status"],
    "products": ["category"],
}
TABLE_HINTS = {
    "order_items": "Contains transaction amounts, revenue, sales, quantities per order.",
    "orders": "Contains order status, order dates, which customer and region placed the order.",
    "customers": "Contains customer signup dates, names, emails, and their region.",
    "products": "Contains product names, categories, and prices.",
    "regions": "Contains region names used to group customers and orders geographically.",
}