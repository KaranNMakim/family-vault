from datetime import date

import pytest

from app.core.estate import Estate
from app.kg.provenance import human
from app.kg.store import NetworkXSQLiteStore
from app.seed import build_vault, family_files, load_family

AS_OF = date(2026, 11, 1)
PASS = "test-passphrase-123"


@pytest.fixture(scope="session")
def families():
    return {f["id"]: f for f in (load_family(p) for p in family_files())}


@pytest.fixture(scope="session")
def seeded_dir(tmp_path_factory, families):
    d = tmp_path_factory.mktemp("vaults")
    for fam in families.values():
        build_vault(fam, d)
    return d


@pytest.fixture
def family_store(seeded_dir, families):
    """Open (read-mostly) store for a seeded family: family_store('family_a')."""
    opened = []

    def _open(fid: str) -> NetworkXSQLiteStore:
        s = NetworkXSQLiteStore.open(seeded_dir / f"{fid}.db", families[fid]["demo_passphrase"])
        opened.append(s)
        return s

    yield _open
    for s in opened:
        s.close()


@pytest.fixture
def fresh(tmp_path, families):
    """A writable copy of a seeded family in tmp_path."""

    def _make(fid: str) -> NetworkXSQLiteStore:
        path = build_vault(families[fid], tmp_path)
        return NetworkXSQLiteStore.open(path, families[fid]["demo_passphrase"])

    return _make


@pytest.fixture
def empty_store(tmp_path):
    s = NetworkXSQLiteStore.create(tmp_path / "empty.db", PASS, {"id": "t", "display_name": "Test"})
    yield s
    s.close()


@pytest.fixture
def est_factory():
    return lambda store: Estate(store, AS_OF)


P = human("test")
