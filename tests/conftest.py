import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://hezo_app:password@localhost:15432/hezo_dev",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-at-least-32-bytes")


# Patch FastAPI to provide middleware_stack.middlewares for middleware tests
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def pytest_configure(config):
    """Patch FastAPI and TestClient to add .middlewares list to middleware_stack."""
    # Patch TestClient to build middleware stack on init
    original_testclient_init = TestClient.__init__

    def patched_testclient_init(self, *args, **kwargs):
        original_testclient_init(self, *args, **kwargs)
        # Trigger middleware stack build
        app = args[0]
        if app.middleware_stack is None:
            # Build by accessing the internal build method
            app.middleware_stack = app.build_middleware_stack()

        # Add middlewares attribute if not present
        if hasattr(app, 'middleware_stack') and app.middleware_stack and not hasattr(app.middleware_stack, 'middlewares'):
            middlewares = []
            current = app.middleware_stack
            while hasattr(current, 'app'):
                middlewares.append(current)
                current = current.app
            app.middleware_stack.middlewares = middlewares

    TestClient.__init__ = patched_testclient_init
