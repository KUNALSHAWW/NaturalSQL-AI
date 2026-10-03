"""Smoke tests for the Streamlit app (no model or API key needed)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_with_hero_and_tabs():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 4
    assert any("Trust none of it" in m.value for m in at.markdown)


def test_playground_blocks_a_stacked_drop_and_allows_a_select():
    at = AppTest.from_file(APP, default_timeout=60).run()
    sql = next(t for t in at.text_area if t.label == "SQL")
    sql.set_value("SELECT name FROM customers; DROP TABLE customers").run()
    assert not at.exception
    assert any("blocked" in m.value.lower() and "exactly one statement" in m.value for m in at.markdown)

    sql = next(t for t in at.text_area if t.label == "SQL")
    sql.set_value("SELECT name FROM customers").run()
    assert any("allowed" in m.value.lower() for m in at.markdown)
