# Fabric User-Login Connector — Plan

## Decision
Use **delegated user login** (Entra email + password) instead of Service Principal.
No app registration, no client secret needed. Each query runs as the user `rahulgupta@cityholdings.com.mm`.

ODBC method: `Authentication=ActiveDirectoryPassword`.

## Security
- Password stored ONLY in gitignored `.env`. Never in code, never echoed.
- ⚠ Password was pasted in chat → ROTATE after this project.
- `.env`, `data/` are in `.gitignore`.

## Hard requirements / caveats
- **MFA must be OFF** for this account. `ActiveDirectoryPassword` cannot satisfy an MFA challenge → login fails if on.
- User must have **read access to the `ods` schema objects** in the `CityPlatforms` warehouse (not just workspace access).
- **LANDMINE (from CityAgent ms_fabric_user connector):** Fabric redirect needs explicit `,1433` AND `Connection Timeout=30` in the conn string, else error `08001 / (26)` "handshake before login". Already baked into `fabric_user_connector.py`.

## Connection string (used by connector)
```
DRIVER={ODBC Driver 18 for SQL Server};
SERVER=<host>,1433;
DATABASE=CityPlatforms;
UID=rahulgupta@cityholdings.com.mm;PWD=***;
Authentication=ActiveDirectoryPassword;
Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
```

## Files created
| File | Purpose |
|---|---|
| `.env` | creds (gitignored) |
| `.gitignore` | excludes .env, data/ |
| `fabric_user_connector.py` | connect / test / discover / query / extract |
| `data/raw/` | landed parquet output |

## Install (one-time)
```bash
brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18
python3 -m pip install pyodbc pandas pyarrow
```

## Run order
```bash
cd ~/Desktop/cityaicfcdemandforcasting
python3 fabric_user_connector.py test        # verify login (whoami + db)
python3 fabric_user_connector.py discover     # dump tables/columns -> data/schema_*.csv
# inspect schema_columns.csv -> find real sales/outlet/sku table+col names
python3 fabric_user_connector.py query "SELECT TOP 20 * FROM ods.<sales_table>"
# edit cmd_extract() SQL with real names, then:
python3 fabric_user_connector.py extract      # land daily-sales panel -> parquet
```

## After extract
Merge promo calendar (loyalty xlsx) on date → feed LightGBM quantile pipeline (`plan.md` Stage 2).

## Next steps
1. Confirm MFA OFF on the account.
2. Install driver + libs.
3. Run `test` → fix any login/handshake error.
4. Run `discover` → map ods.* tables to needs (sales/outlet/sku/inventory).
5. Fill real names in `cmd_extract()` → land data.
