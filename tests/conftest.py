import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://hezo_app:password@localhost:15432/hezo_dev",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-at-least-32-bytes")
