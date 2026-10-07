"""Load the integration's parser/api/const modules without Home Assistant.

``custom_components/fddb/__init__.py`` imports Home Assistant, so the real package
is never imported. Instead, lightweight placeholder packages are registered in
``sys.modules`` and only the HA-free submodules are loaded from their files.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT / "custom_components" / "fddb"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _register_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


_register_package("custom_components", ROOT / "custom_components")
_register_package("custom_components.fddb", PACKAGE_DIR)

const = importlib.import_module("custom_components.fddb.const")
parser = importlib.import_module("custom_components.fddb.parser")
api = importlib.import_module("custom_components.fddb.api")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def load_fixture():
    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load
