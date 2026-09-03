import pytest

pytest_plugins = []

def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: async tests")
