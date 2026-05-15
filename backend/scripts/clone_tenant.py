"""Clone all data from SRC tenant to DST tenant (wipes DST first). One transaction, rolls back on error.

Usage:
    docker compose run --rm backend python scripts/clone_tenant.py --src 13 --dst 3

Tables copied (in FK-safe order): tenant_settings, users, menu_items, model_versions,
openai_usage, audit_logs, training_jobs, transactions (+items), payments, receipts,
stock_movements.
"""
import argparse
import os
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _db_url() -> str:
    # Backend .env uses +asyncpg; strip it for psycopg2. Container sees db at host "db".
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        return "host=db port=5432 dbname=geyam user=pos_user password=pos_pass"
    return raw.replace("postgresql+asyncpg://", "postgresql://").replace("@localhost:5433", "@db:5432")


SCOPED_WIPE_ORDER = [
    "payments", "receipts", "transactions",  # transactions cascades transaction_items
    "stock_movements", "training_jobs", "audit_logs", "model_versions", "openai_usage",
    "menu_items", "users", "tenant_settings",
]


def _cols(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=%s AND table_schema='public' ORDER BY ordinal_position",
        (table,),
    )
    return [r["column_name"] for r in cur.fetchall()]


def _copy_rows(cur, table: str, src: int, dst: int,
               id_remap: dict[str, dict[int, int]],
               fk_map: dict[str, str]) -> dict[int, int]:
    """Copy rows of `table` from tenant src → dst, remapping PK + listed FK columns.

    Returns {old_id: new_id} for the copied table's own PK (if it has `id`).
    """
    cols = _cols(cur, table)
    has_id = "id" in cols
    insert_cols = [c for c in cols if c != "id"]
    select_cols_sql = ", ".join(f'"{c}"' for c in cols)
    order_sql = "ORDER BY id" if has_id else ""
    cur.execute(f'SELECT {select_cols_sql} FROM "{table}" WHERE tenant_id = %s {order_sql}', (src,))
    rows = cur.fetchall()
    result: dict[int, int] = {}
    for row in rows:
        row = dict(row)
        old_id = row.pop("id", None) if has_id else None
        row["tenant_id"] = dst
        # Remap FK columns
        for fk_col, ref_table in fk_map.items():
            if fk_col in row and row[fk_col] is not None:
                mapping = id_remap.get(ref_table, {})
                new_fk = mapping.get(row[fk_col])
                row[fk_col] = new_fk  # None if unknown — acceptable only if FK is nullable
        values = [Jsonb(row[c]) if isinstance(row[c], (dict, list)) else row[c] for c in insert_cols]
        placeholders = ", ".join(["%s"] * len(insert_cols))
        col_list = ", ".join(f'"{c}"' for c in insert_cols)
        if has_id:
            cur.execute(
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) RETURNING id',
                values,
            )
            new_id = cur.fetchone()["id"]
            result[old_id] = new_id
        else:
            cur.execute(
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})',
                values,
            )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=int, required=True)
    ap.add_argument("--dst", type=int, required=True)
    args = ap.parse_args()
    if args.src == args.dst:
        print("src and dst cannot be equal", file=sys.stderr)
        return 2

    conn = psycopg.connect(_db_url(), autocommit=False)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            # Sanity check both tenants exist
            cur.execute("SELECT id, handle, name FROM tenants WHERE id IN (%s, %s) ORDER BY id",
                        (args.src, args.dst))
            rows = cur.fetchall()
            if len(rows) != 2:
                print(f"Both tenants must exist: found {rows}", file=sys.stderr)
                return 2
            print(f"Cloning tenant {args.src} → {args.dst}")
            for r in rows:
                print(f"  #{r['id']} {r['handle']} — {r['name']}")

            # 1) Wipe DST
            for t in SCOPED_WIPE_ORDER:
                cur.execute(f'DELETE FROM "{t}" WHERE tenant_id = %s', (args.dst,))
                print(f"  wiped {t}: {cur.rowcount} rows")

            # 2) Copy in dependency order, collecting ID maps
            id_remap: dict[str, dict[int, int]] = {}

            # tenant_settings — no FKs among tenant-scoped tables
            id_remap["tenant_settings"] = _copy_rows(cur, "tenant_settings", args.src, args.dst, id_remap, {})

            # users
            id_remap["users"] = _copy_rows(cur, "users", args.src, args.dst, id_remap, {})
            print(f"  users: {len(id_remap['users'])} copied")

            # menu_items
            id_remap["menu_items"] = _copy_rows(cur, "menu_items", args.src, args.dst, id_remap, {})
            print(f"  menu_items: {len(id_remap['menu_items'])} copied")

            # model_versions — no FKs
            id_remap["model_versions"] = _copy_rows(cur, "model_versions", args.src, args.dst, id_remap, {})

            # openai_usage — no FKs to tenant-scoped tables (just tenant_id)
            id_remap["openai_usage"] = _copy_rows(cur, "openai_usage", args.src, args.dst, id_remap, {})

            # training_jobs — FK: menu_item_id → menu_items (SET NULL)
            id_remap["training_jobs"] = _copy_rows(cur, "training_jobs", args.src, args.dst, id_remap,
                                                   {"menu_item_id": "menu_items"})

            # audit_logs — FK: user_id → users
            id_remap["audit_logs"] = _copy_rows(cur, "audit_logs", args.src, args.dst, id_remap,
                                                 {"user_id": "users"})

            # transactions — FKs: staff_id → users, voided_by → users
            #   (receipt_email is a plain text column; customers/POs/suppliers are out of scope)
            id_remap["transactions"] = _copy_rows(cur, "transactions", args.src, args.dst, id_remap,
                                                   {"staff_id": "users", "voided_by": "users"})
            print(f"  transactions: {len(id_remap['transactions'])} copied")

            # transaction_items — not tenant-scoped
            cur.execute('SELECT * FROM "transaction_items" WHERE transaction_id IN '
                        '(SELECT id FROM "transactions" WHERE tenant_id = %s)', (args.src,))
            for row in cur.fetchall():
                row = dict(row)
                row.pop("id", None)
                row["transaction_id"] = id_remap["transactions"].get(row["transaction_id"])
                row["menu_item_id"] = id_remap["menu_items"].get(row["menu_item_id"]) if row.get("menu_item_id") else None
                cols = list(row.keys())
                cur.execute(
                    f'INSERT INTO "transaction_items" ({", ".join(cols)}) VALUES ({", ".join(["%s"]*len(cols))})',
                    [Jsonb(row[c]) if isinstance(row[c], (dict, list)) else row[c] for c in cols],
                )

            # payments — FK: transaction_id → transactions
            id_remap["payments"] = _copy_rows(cur, "payments", args.src, args.dst, id_remap,
                                               {"transaction_id": "transactions"})

            # receipts — FK: transaction_id → transactions
            id_remap["receipts"] = _copy_rows(cur, "receipts", args.src, args.dst, id_remap,
                                               {"transaction_id": "transactions"})

            # stock_movements — FKs: menu_item_id → menu_items, created_by → users
            id_remap["stock_movements"] = _copy_rows(cur, "stock_movements", args.src, args.dst, id_remap,
                                                     {"menu_item_id": "menu_items", "created_by": "users"})

        conn.commit()
        print("COMMIT — clone complete.")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"ROLLBACK — {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
