"""
Microsoft Fabric — User (delegated) login connector.

Auth: ODBC Authentication=ActiveDirectoryPassword (Entra email + password).
No service principal, no app registration needed.
Caveat: fails if MFA is enabled on the account.

Usage:
    python3 fabric_user_connector.py test          # connectivity + whoami
    python3 fabric_user_connector.py discover       # list tables/columns in schema
    python3 fabric_user_connector.py query "SELECT TOP 10 * FROM ods.x"
    python3 fabric_user_connector.py extract        # land daily-sales panel to parquet

Requires:
    brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release
    HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18
    python3 -m pip install pyodbc pandas python-dotenv pyarrow
"""
import os, sys, pathlib
import pyodbc
import pandas as pd

# --- load .env (no dep on python-dotenv; OPTIONAL — prod passes env via compose) ---
ROOT = pathlib.Path(__file__).parent
_envf = ROOT / ".env"
if _envf.exists():
    for line in _envf.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Read with .get so importing this module (src/extract.py does) never crashes on a box
# that only configures the LIVE read path (FABRIC_SQL_ENDPOINT). Missing extract creds
# fail with a clear error at connect() time instead of an import-time KeyError.
SERVER   = os.environ.get("FABRIC_SERVER", "")
DATABASE = os.environ.get("FABRIC_DATABASE", "")
SCHEMA   = os.environ.get("FABRIC_SCHEMA", "ods")
USER     = os.environ.get("FABRIC_USER", "")
PASSWORD = os.environ.get("FABRIC_PASSWORD", "")


def connect():
    if not (SERVER and DATABASE and USER and PASSWORD):
        raise RuntimeError(
            "Fabric extract credentials missing — set FABRIC_SERVER, FABRIC_DATABASE, "
            "FABRIC_USER, FABRIC_PASSWORD in the environment (.env / .env.prod).")
    # LANDMINE: Fabric redirect needs explicit ,1433 + Connection Timeout=30,
    # else 08001/(26) handshake-before-login error.
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SERVER},1433;"
        f"DATABASE={DATABASE};"
        f"UID={USER};PWD={PASSWORD};"
        "Authentication=ActiveDirectoryPassword;"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def q(sql, params=None):
    with connect() as c:
        return pd.read_sql(sql, c, params=params)


def cmd_test():
    df = q("SELECT SUSER_SNAME() AS login_name, DB_NAME() AS db, GETDATE() AS server_time")
    print(df.to_string(index=False))
    print("OK — connected.")


def cmd_discover():
    tabs = q("""
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)
    print("=== TABLES ===")
    print(tabs.to_string(index=False))
    tabs.to_csv(ROOT / "data" / "schema_tables.csv", index=False)

    cols = q("""
        SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ?
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """, params=[SCHEMA])
    cols.to_csv(ROOT / "data" / "schema_columns.csv", index=False)
    print(f"\n=== COLUMNS in [{SCHEMA}] -> data/schema_columns.csv ({len(cols)} rows) ===")
    print(cols.head(60).to_string(index=False))


def cmd_query(sql):
    df = q(sql)
    print(df.to_string(index=False))
    print(f"\n[{len(df)} rows]")


def cmd_profile(table=None):
    """Profile every column of a table: type, null%, approx distinct, min/max, samples."""
    table = table or f"{SCHEMA}.CR_Transactions"
    sch, tbl = table.split(".") if "." in table else (SCHEMA, table)
    cols = q("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=? AND TABLE_NAME=?
        ORDER BY ORDINAL_POSITION
    """, params=[sch, tbl])
    total = int(q(f"SELECT COUNT(*) n FROM {table}")["n"].iloc[0])
    rows = []
    for _, r in cols.iterrows():
        col, dt = r["COLUMN_NAME"], r["DATA_TYPE"]
        b = f"[{col}]"
        nn = int(q(f"SELECT COUNT(*) n FROM {table} WHERE {b} IS NOT NULL")["n"].iloc[0])
        try:
            dist = int(q(f"SELECT APPROX_COUNT_DISTINCT({b}) n FROM {table}")["n"].iloc[0])
        except Exception:
            dist = None
        mn = mx = None
        if dt in ("decimal", "bigint", "int", "datetime2", "datetime", "date", "float"):
            mm = q(f"SELECT MIN({b}) mn, MAX({b}) mx FROM {table}")
            mn, mx = mm["mn"].iloc[0], mm["mx"].iloc[0]
        try:
            sv = q(f"SELECT DISTINCT TOP 5 {b} v FROM {table} WHERE {b} IS NOT NULL")["v"].astype(str).tolist()
        except Exception:
            sv = []
        rows.append({
            "column": col, "type": dt,
            "null_pct": round(100 * (total - nn) / total, 2) if total else None,
            "approx_distinct": dist, "min": str(mn), "max": str(mx),
            "samples": " | ".join(sv),
        })
        print(f"  {col:22} {dt:11} null%={rows[-1]['null_pct']:>6} distinct={dist}")
    out = pd.DataFrame(rows)
    dest = ROOT / "data" / f"metadata_{tbl}.csv"
    out.to_csv(dest, index=False)
    print(f"\nTotal rows: {total:,}\nProfile -> {dest}")
    return out, total


def cmd_extract():
    # TEMPLATE — replace table/column names after discover step.
    sql = """
        SELECT
            CAST(s.txn_datetime AS date) AS sale_date,
            s.outlet_id,
            s.sku_id,
            SUM(s.qty)        AS units,
            SUM(s.net_amount) AS revenue
        FROM ods.sales s
        WHERE s.txn_datetime >= DATEADD(day, -730, CAST(GETDATE() AS date))
        GROUP BY CAST(s.txn_datetime AS date), s.outlet_id, s.sku_id
    """
    df = q(sql)
    out = ROOT / "data" / "raw" / "daily_sales_panel.parquet"
    df.to_parquet(out, index=False)
    print(f"Landed {len(df)} rows -> {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "test":        cmd_test()
    elif cmd == "discover":  cmd_discover()
    elif cmd == "query":     cmd_query(sys.argv[2])
    elif cmd == "profile":   cmd_profile(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "extract":   cmd_extract()
    else:                    print(__doc__)
