from naturalsql.schema import SchemaLinker, tokens


def test_introspection_finds_tables_keys_and_counts(schema):
    assert {"customers", "orders", "order_items", "products", "categories", "employees", "users"} <= set(schema.tables)
    orders = schema.tables["orders"]
    assert orders.row_count == 500
    assert any(fk.ref_table == "customers" for fk in orders.foreign_keys)
    assert schema.tables["customers"].column("id").primary_key
    assert schema.dialect == "sqlite"


def test_small_enumerations_are_detected(schema):
    seg = schema.tables["customers"].column("segment")
    assert seg.distinct_values == ["Consumer", "Corporate", "Small Business"]
    assert schema.tables["customers"].column("name").distinct_values is None


def test_render_contains_ddl_comments_and_foreign_keys(schema):
    ddl = schema.render(["orders", "customers"])
    assert "CREATE TABLE orders" in ddl and "FOREIGN KEY (customer_id) REFERENCES customers(id)" in ddl
    assert "values: Consumer, Corporate, Small Business" in ddl and "about 500 rows" in ddl


def test_tokenizer_splits_cases_and_stems():
    assert tokens("customerOrders") == ["customer", "order"]
    assert tokens("Which countries have the most customers?") == ["country", "customer"]


def test_value_linking_finds_literals(schema):
    hints = SchemaLinker(schema).value_hints("How many customers live in France or Germany?")
    assert ("customers", "country", "France") in hints and ("customers", "country", "Germany") in hints


def test_value_linking_ignores_unrelated_text(schema):
    assert SchemaLinker(schema).value_hints("how many rows are there") == []


def test_linking_selects_relevant_tables_when_schema_is_large(schema):
    linker = SchemaLinker(schema, max_tables=2, small_schema=3)
    linked = linker.link("What is the average salary in each department?")
    assert linked.tables[0] == "employees"
    assert "users" not in linked.tables
    assert "CREATE TABLE employees" in linked.ddl


def test_linking_expands_foreign_keys_for_joins(schema):
    linker = SchemaLinker(schema, max_tables=2, small_schema=3)
    linked = linker.link("total quantity sold per category name")
    assert {"order_items", "products", "categories"} <= set(linked.tables)


def test_small_schema_is_passed_whole(schema):
    linked = SchemaLinker(schema).link("anything")
    assert set(linked.tables) == set(schema.tables)


def test_value_hints_only_for_linked_tables(schema):
    linker = SchemaLinker(schema, max_tables=1, small_schema=2)
    linked = linker.link("customers from France")
    assert any("France" in h for h in linked.value_hints)
