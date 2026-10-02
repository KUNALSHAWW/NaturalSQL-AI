import pytest

from naturalsql.bench import retail_db
from naturalsql.config import Settings
from naturalsql.executor import ReadOnlyExecutor
from naturalsql.pipeline import Text2SQL
from naturalsql.schema import SchemaInfo


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("db") / "retail.db"
    retail_db.build(p, seed=3, n_customers=120, n_orders=500)
    return p


@pytest.fixture(scope="session")
def executor(db_path):
    return ReadOnlyExecutor(f"sqlite:///{db_path}", timeout_s=5, max_rows=200)


@pytest.fixture(scope="session")
def schema(executor):
    return SchemaInfo.from_engine(executor.engine)


def make_engine(executor, schema, llm, memory=None, **overrides):
    settings = Settings(
        provider="ollama",
        n_candidates=overrides.pop("n_candidates", 1),
        max_repairs=overrides.pop("max_repairs", 2),
        denied_columns=set(retail_db.DENIED_COLUMNS),
        **overrides,
    )
    return Text2SQL(executor, llm, settings, schema=schema, memory=memory)
