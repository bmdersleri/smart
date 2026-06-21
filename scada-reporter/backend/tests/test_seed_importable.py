"""Smoke test: seed scripts are importable as modules without sys.path hacks.

Importing is safe — all three scripts guard seeding logic under ``if __name__ == "__main__"``,
so no DB writes occur here.
"""

import importlib


def test_seed_users_importable_and_has_main():
    module = importlib.import_module("app.seed_users")
    assert callable(module.main), "app.seed_users must expose a callable 'main'"


def test_seed_tags_importable_and_has_main():
    module = importlib.import_module("app.seed_tags")
    assert callable(module.main), "app.seed_tags must expose a callable 'main'"


def test_seed_catalog_importable_and_has_main():
    module = importlib.import_module("app.seed_catalog")
    assert callable(module.main), "app.seed_catalog must expose a callable 'main'"
