from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.iam import models as iam_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.orders import models as orders_models  # noqa: F401
from app.modules.production import models as production_models  # noqa: F401
from app.modules.purchasing import models as purchasing_models  # noqa: F401
from app.modules.sales import models as sales_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    return configured_url if configured_url else get_settings().DATABASE_URL


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    if type_ == "schema":
        return name in {"iam", "sales", "purchasing", "production", "inventory", "audit"}
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
