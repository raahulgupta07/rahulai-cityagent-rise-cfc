# Microsoft Fabric — Connection & Data Extraction Plan

## Status / Blockers
1. **Missing real Service Principal creds.** Guide has `Client ID = "Your email"` and `Client Secret = "Your current password"` — placeholders, not valid. SP auth requires:
   - `Client ID` = app registration **Application (client) ID** (GUID)
   - `Client Secret` = secret **VALUE** (Azure → App registrations → Certificates & secrets → New client secret → copy Value)
   - Get from whoever owns the Entra app registration.
2. **No local driver.** Machine lacks pyodbc + MS ODBC Driver 18 + azure-identity. Install before querying.
3. **SP must be granted workspace access** (Fabric → workspace → Manage access → Member/Contributor) AND tenant setting "Service principals can use Fabric APIs" = ON. Guide says 90% of failures are these two.

## Valid connection params
| Field | Value |
|---|---|
| Server (host only) | `frhyucu26ckupeg6zzmno4bsde-utccgytlptlefo5yizfdykvaly.datawarehouse.fabric.microsoft.com` |
| Database | `CityPlatforms` |
| Schema | `ods` |
| Tenant ID | `0a8a4f2c-f09a-4795-90de-ce58d7703219` |
| Client ID | TODO — real GUID |
| Client Secret | TODO — real secret VALUE |

⚠ Use host only. NO `,1433` port, NO db suffix in host string.

## Auth method — best practice
Fabric SQL endpoint does NOT accept SP user/password in the ODBC connection string directly.
Correct pattern = **fetch an Entra access token via MSAL/azure-identity, inject it into ODBC via attribute 1256 (SQL_COPT_SS_ACCESS_TOKEN)**.

Scope: `https://database.windows.net/.default`

This is the same pattern the CityAgent `MsFabricClient` connector uses (token-based, not ActiveDirectoryServicePrincipal in conn str — more reliable across Fabric redirects).

## Install (local, one-time)
```bash
# MS ODBC Driver 18 (mac)
brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release
brew update
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18

# python libs
python3 -m pip install pyodbc azure-identity
```

## Connection code (token-based)
```python
import struct, pyodbc
from azure.identity import ClientSecretCredential

TENANT   = "0a8a4f2c-f09a-4795-90de-ce58d7703219"
CLIENT   = "<REAL_CLIENT_ID_GUID>"
SECRET   = "<REAL_CLIENT_SECRET_VALUE>"
SERVER   = "frhyucu26ckupeg6zzmno4bsde-utccgytlptlefo5yizfdykvaly.datawarehouse.fabric.microsoft.com"
DATABASE = "CityPlatforms"

cred  = ClientSecretCredential(TENANT, CLIENT, SECRET)
token = cred.get_token("https://database.windows.net/.default").token
tok   = token.encode("utf-16-le")
tokstruct = struct.pack(f"<I{len(tok)}s", len(tok), tok)

SQL_COPT_SS_ACCESS_TOKEN = 1256
conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SERVER},1433;DATABASE={DATABASE};"
    f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;",
    attrs_before={SQL_COPT_SS_ACCESS_TOKEN: tokstruct},
)
```
Note: `,1433` belongs in the ODBC `SERVER=` string here (driver needs it); only the *Fabric UI host field* must omit it.

## Discovery queries (run first — learn the schema)
```sql
-- list tables in target schema
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- columns of a candidate sales table
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA='ods'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- row counts / date span sanity
SELECT COUNT(*) FROM ods.<sales_table>;
SELECT MIN(<date_col>), MAX(<date_col>) FROM ods.<sales_table>;
```

## Data we NEED for forecasting (map to Fabric tables)
| Need | Likely table | Grain |
|---|---|---|
| Daily sales (TARGET) | ods.sales / ods.transactions / ods.pos_* | line item or daily agg |
| Outlet master | ods.store / ods.outlet | one row/outlet |
| SKU master | ods.product / ods.item | one row/SKU |
| Promo calendar | already have (loyalty xlsx) | campaign |
| Inventory / orders | ods.stock / ods.warehouse_order | daily |

## Extraction query — daily sales panel (template)
Aggregate to the model grain `(outlet, sku, day)` server-side. Don't pull raw line items if huge.
```sql
SELECT
    CAST(s.txn_datetime AS date)  AS sale_date,
    s.outlet_id,
    s.sku_id,
    SUM(s.qty)                    AS units,
    SUM(s.net_amount)             AS revenue
FROM ods.sales s
WHERE s.txn_datetime >= DATEADD(day, -730, CAST(GETDATE() AS date))   -- 2yr history
GROUP BY CAST(s.txn_datetime AS date), s.outlet_id, s.sku_id;
```
(Replace names after discovery.)

## Best practices
- **Push aggregation to Fabric** (GROUP BY in SQL) — pull the panel, not raw rows. Less data, faster.
- **Incremental pull**: after first full load, pull only `sale_date > last_loaded` (watermark). Store local parquet.
- **Read-only SP**: grant the SP only what's needed; this is reporting, not writes.
- **Land raw to parquet** in this folder (`data/raw/`) → reproducible, offline model dev, no repeated cloud hits.
- **Token caching**: token ~1hr TTL; refresh per session, don't fetch per query.
- **Validate on land**: row counts, null %, date continuity, negative qty (returns) before training.
- **Never commit secrets**: put creds in `.env` (gitignored), not in code.

## Next steps (in order)
1. Get real Client ID + Client Secret VALUE.
2. Confirm SP granted workspace access + tenant setting ON.
3. Install driver + libs (commands above).
4. Run discovery queries → map ods.* tables to the needs table.
5. Build extraction script → land daily-sales panel to `data/raw/*.parquet`.
6. Merge promo calendar (loyalty xlsx) → feed LightGBM pipeline (`plan.md` Stage 2).
