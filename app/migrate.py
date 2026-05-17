"""
app/migrate.py
Database migration helper. Safely adds new columns to existing tables
without losing your data — like ALTER TABLE in MySQL, but automatic.

How it works:
  - Compares your current Python models against the actual database
  - Finds columns that exist in the model but not in the database
  - Adds those columns with ALTER TABLE statements
  - Leaves your data intact

Run with:
    python -m app.migrate

For schema changes that can't be auto-detected (renames, type changes,
drops), use Alembic. This script handles 90% of common cases.
"""
import sys
from sqlalchemy import inspect, text

from app.database import engine, Base
import app.models  # noqa: F401  - registers all models with Base


def get_db_columns(table_name: str) -> set:
    """Return the set of column names currently in the database for this table."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def get_model_columns(table) -> dict:
    """Return {col_name: sqlalchemy_column} for the model."""
    return {col.name: col for col in table.columns}


def sql_type_for(col) -> str:
    """Best-effort mapping from SQLAlchemy column to SQLite column type."""
    type_str = str(col.type).upper()
    if "INT" in type_str:    return "INTEGER"
    if "FLOAT" in type_str:  return "REAL"
    if "NUMERIC" in type_str:return "REAL"
    if "BOOL" in type_str:   return "INTEGER"
    if "DATE" in type_str:   return "DATE"
    if "TIME" in type_str:   return "DATETIME"
    if "TEXT" in type_str:   return "TEXT"
    return "TEXT"  # VARCHAR, STRING, etc. all map to TEXT in SQLite


def run():
    print()
    print("=" * 60)
    print("  TIMESHEET AI — Database migration")
    print("=" * 60)
    print()

    # 1) Make sure all NEW tables exist
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables.keys())
    new_tables = model_tables - existing_tables

    if new_tables:
        print(f"Step 1: Creating {len(new_tables)} new table(s)...")
        Base.metadata.create_all(bind=engine)
        for t in new_tables:
            print(f"  ✓ Created table: {t}")
    else:
        print("Step 1: No new tables to create  ✓")
    print()

    # 2) Check each table for new columns
    print("Step 2: Checking for new columns...")
    added_anything = False
    with engine.connect() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name in new_tables:
                continue  # already done in step 1

            db_cols    = get_db_columns(table_name)
            model_cols = get_model_columns(table)
            missing    = set(model_cols.keys()) - db_cols

            for col_name in missing:
                col = model_cols[col_name]
                col_type = sql_type_for(col)
                nullable = "" if col.nullable else " NOT NULL"
                default  = ""
                if col.default is not None and not callable(col.default.arg):
                    val = col.default.arg
                    default = f" DEFAULT '{val}'" if isinstance(val, str) else f" DEFAULT {val}"

                # SQLite ALTER TABLE limitation: NOT NULL requires a default
                if not col.nullable and not default:
                    default = " DEFAULT ''" if col_type == "TEXT" else " DEFAULT 0"

                sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{default}"
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"  ✓ Added column: {table_name}.{col_name} ({col_type})")
                    added_anything = True
                except Exception as e:
                    print(f"  ✗ Failed to add {table_name}.{col_name}: {e}")

    if not added_anything and not new_tables:
        print("  No new columns to add — your database is up to date  ✓")
    print()

    print("=" * 60)
    print("  ✓ Migration complete")
    print("=" * 60)
    print()
    print("  NOTE: This script handles adding NEW tables and NEW columns.")
    print("  For renames, type changes, or removed columns, use Alembic.")
    print()


if __name__ == "__main__":
    run()