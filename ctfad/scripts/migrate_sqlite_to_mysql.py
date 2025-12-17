"""Copy all HHF-ADCTF data from the local SQLite file into a MySQL database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

TABLE_ORDER: Sequence[str] = (
    "admin_user",
    "game_config",
    "team",
    "team_credential",
    "challenge",
    "flag_access_token",
    "flag",
    "flag_submission",
    "sla_result",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        default="db/ctfad.db",
        help="Path to the source SQLite database (default: %(default)s)",
    )
    parser.add_argument(
        "--mysql",
        default="mysql+pymysql://ctfad:ctfad@localhost/ctfad",
        help=(
            "SQLAlchemy URL for the destination MySQL database "
            "(default: %(default)s). "
            "Use the same credentials you configured in docker-compose/.env."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Connect to both databases but do not write anything to MySQL.",
    )
    return parser.parse_args()


def ensure_sqlite_path(path: str) -> Path:
    sqlite_path = Path(path).expanduser().resolve()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found at {sqlite_path}")
    return sqlite_path


def build_engines(sqlite_path: Path, mysql_url: str) -> tuple[Engine, Engine]:
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}", future=True)
    mysql_engine = create_engine(mysql_url, future=True)
    return sqlite_engine, mysql_engine


def migrate(sqlite_engine: Engine, mysql_engine: Engine, dry_run: bool = False) -> None:
    metadata = MetaData()
    metadata.reflect(bind=mysql_engine, only=TABLE_ORDER)

    with sqlite_engine.connect() as src_conn, mysql_engine.begin() as dst_conn:
        if dry_run:
            print("DRY RUN: no changes will be applied to MySQL.")
        else:
            dst_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))

        for table_name in TABLE_ORDER:
            if table_name not in metadata.tables:
                print(f"[WARN] Table '{table_name}' missing from MySQL schema; skipping.")
                continue

            table: Table = metadata.tables[table_name]
            rows = src_conn.execute(text(f"SELECT * FROM {table_name}")).mappings().all()
            count = len(rows)
            if dry_run:
                print(f"[DRY] {table_name}: found {count} rows to transfer.")
                continue

            dst_conn.execute(table.delete())
            if count:
                dst_conn.execute(table.insert(), rows)
            print(f"[OK] {table_name}: migrated {count} rows.")

        if not dry_run:
            dst_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            print("Migration complete.")


def main() -> int:
    args = parse_args()
    try:
        sqlite_path = ensure_sqlite_path(args.sqlite)
        sqlite_engine, mysql_engine = build_engines(sqlite_path, args.mysql)
        migrate(sqlite_engine, mysql_engine, dry_run=args.dry_run)
    except (FileNotFoundError, SQLAlchemyError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
