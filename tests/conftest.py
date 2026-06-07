import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://hezo_app:password@localhost:15432/hezo_dev",
)
