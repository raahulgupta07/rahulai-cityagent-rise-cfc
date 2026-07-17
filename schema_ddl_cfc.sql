/* =============================================================================
   CFC Bakery — HUB_REPORTING_DB  CREATE TABLE definitions
   Schemas: cfc (masters/dims) + edm (facts)
   Source of truth: live profile 2026-06-24 + extracted parquet schemas.

   NOTES
   - Types reconstructed from extracted parquet + schema_cfc_bakery.md.
   - Cols that profile as FLOAT/DOUBLE *only because of NULLs* are marked
     /* int, nullable */ — true domain is integer id.
   - DayKey is VARCHAR(8) 'YYYYMMDD' (NOT a date) — cast on use.
   - Fact grains: Sales_Summary = Day x Branch x Product x CardType.
   - [DATA WE HAVE] = extracted locally to data/raw/*.parquet.
   - [DOC ONLY]     = profiled in Fabric, not extracted; cols inferred from doc.
   ============================================================================= */


/* ============================ cfc  (DIMENSIONS) ============================ */

/* Dim_Channel (7 rows) — sales/loyalty channel lookup.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Dim_Channel] (
    ChannelId    INT            NOT NULL,   -- PK
    ChannelName  NVARCHAR(200)  NULL,
    ChannelCode  NVARCHAR(50)   NULL,
    CreateDate   DATETIME2      NULL,
    WriteDate    DATETIME2      NULL,
    LoadDate     DATETIME2      NULL,        -- ETL load stamp
    CONSTRAINT PK_Dim_Channel PRIMARY KEY (ChannelId)
);

/* Dim_Company (1 row) — legal/operating company.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Dim_Company] (
    CompanyId    INT            NOT NULL,   -- PK
    CompanyName  NVARCHAR(200)  NULL,
    LoadDate     DATETIME2      NULL,
    CONSTRAINT PK_Dim_Company PRIMARY KEY (CompanyId)
);

/* Dim_CostCenter (163 rows) — accounting cost centre.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Dim_CostCenter] (
    CostCenterId    INT            NOT NULL,   -- PK
    CostCenterName  NVARCHAR(200)  NULL,
    Description     NVARCHAR(400)  NULL,
    CreateDate      DATETIME2      NULL,
    WriteDate       DATETIME2      NULL,
    LoadDate        DATETIME2      NULL,
    CONSTRAINT PK_Dim_CostCenter PRIMARY KEY (CostCenterId)
);

/* Dim_ProfitCenter (85 rows) — accounting profit centre.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Dim_ProfitCenter] (
    ProfitCenterId    INT            NOT NULL,   -- PK
    ProfitCenterName  NVARCHAR(200)  NULL,
    Description       NVARCHAR(400)  NULL,
    CreateDate        DATETIME2      NULL,
    WriteDate         DATETIME2      NULL,
    LoadDate          DATETIME2      NULL,
    CONSTRAINT PK_Dim_ProfitCenter PRIMARY KEY (ProfitCenterId)
);

/* Dim_Segment (9 rows) — brand/format segment (Seasons, NBH, Bistro, Gong Cha...).  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Dim_Segment] (
    SegmentId    INT            NOT NULL,   -- PK
    SegmentName  NVARCHAR(200)  NULL,
    Description  NVARCHAR(400)  NULL,
    CreateDate   DATETIME2      NULL,
    WriteDate    DATETIME2      NULL,
    LoadDate     DATETIME2      NULL,
    CONSTRAINT PK_Dim_Segment PRIMARY KEY (SegmentId)
);


/* ============================ cfc  (MASTERS) ============================ */

/* Ref_Branch_Master (98 rows) — outlet master. 84 of 98 have sales.  [DATA WE HAVE]
   Segment/CostCenter/ProfitCenter stored as NAME strings (denormalised).
   StockInId/StockOutId link to Ref_StockWarehouse_Master. */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_Branch_Master] (
    BranchId       INT            NOT NULL,   -- PK
    BranchName     NVARCHAR(200)  NULL,
    BranchCode     NVARCHAR(50)   NULL,        -- e.g. SBBAGO, SBIC, GCHD
    V5LocationCode NVARCHAR(50)   NULL,
    CompanyId      INT            NULL,        -- -> Dim_Company
    CompanyName    NVARCHAR(200)  NULL,
    Segment        NVARCHAR(200)  NULL,        -- denormalised segment name
    CostCenter     NVARCHAR(200)  NULL,        -- denormalised name
    ProfitCenter   NVARCHAR(200)  NULL,        -- denormalised name
    PartnerId      INT            NULL,        -- -> Ref_Partner_Master (all-null in extract)
    StockInId      INT            NULL,        -- -> Ref_StockWarehouse_Master (inbound)
    StockOutId     INT            NULL,        -- -> Ref_StockWarehouse_Master (supplying WH)
    MainBranch     INT            NULL,        -- flag / parent branch id
    OpeningDate    DATETIME2      NULL,
    TimingInfo     NVARCHAR(200)  NULL,        -- trading hours text
    ChannelId      INT            NULL,        -- -> Dim_Channel (~14% null)
    Address        NVARCHAR(500)  NULL,        -- used to derive city for weather join
    Telephone      NVARCHAR(100)  NULL,
    CONSTRAINT PK_Ref_Branch_Master PRIMARY KEY (BranchId)
);

/* Ref_Product_Master (29,515 rows; 3,580 actually sell) — SKU master.  [DATA WE HAVE]
   5-level category hierarchy. Filter CatLvl1_Name='FG' for sellable finished goods.
   (Source also carries CatLvl1..5_Id; not extracted — add if needed.) */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_Product_Master] (
    ProductId       INT            NOT NULL,   -- PK
    ProductName     NVARCHAR(300)  NULL,
    ProductCode     NVARCHAR(100)  NULL,
    OldProductCode  NVARCHAR(100)  NULL,
    ListPrice       DECIMAL(18,4)  NULL,        -- selling price (margin proxy; NO cost in source)
    UoM             NVARCHAR(50)   NULL,
    Factor          DECIMAL(18,6)  NULL,        -- UoM conversion factor
    Active          BIT            NULL,
    CategoryId      INT            NULL,
    CategoryName    NVARCHAR(200)  NULL,
    CatLvl1_Name    NVARCHAR(100)  NULL,        -- FG / Premix / RM / Semi-FG / MTN / ADM / B2B
    CatLvl2_Name    NVARCHAR(100)  NULL,
    CatLvl3_Name    NVARCHAR(100)  NULL,
    CatLvl4_Name    NVARCHAR(100)  NULL,
    CatLvl5_Name    NVARCHAR(100)  NULL,
    CONSTRAINT PK_Ref_Product_Master PRIMARY KEY (ProductId)
);

/* Ref_Partner_Master (4,918 rows) — partners/suppliers with geo.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_Partner_Master] (
    PartnerId         INT            NOT NULL,   -- PK
    PartnerName       NVARCHAR(300)  NULL,
    CompanyId         INT            NULL,
    DisplayName       NVARCHAR(300)  NULL,
    ActiveFlag        BIT            NULL,
    Type              NVARCHAR(100)  NULL,        -- partner type/category
    PartnerLatitude   DECIMAL(9,6)   NULL,
    PartnerLongitude  DECIMAL(9,6)   NULL,
    Email             NVARCHAR(200)  NULL,
    IsCompany         BIT            NULL,
    LoadDate          DATETIME2      NULL,
    CONSTRAINT PK_Ref_Partner_Master PRIMARY KEY (PartnerId)
);

/* Ref_StockLocation_Master (1,409 rows) — stock locations, 3-level hierarchy.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_StockLocation_Master] (
    StockLocId        INT            NOT NULL,   -- PK
    StockLocName      NVARCHAR(300)  NULL,
    ParentPathName    NVARCHAR(500)  NULL,        -- full hierarchy path
    ActiveFlag        BIT            NULL,
    Usage             NVARCHAR(100)  NULL,        -- location usage type
    BranchId          INT            NULL,        -- -> Ref_Branch_Master (all-null in extract)
    CompanyId         INT            NULL,
    StockLocLvl1_Name NVARCHAR(200)  NULL,
    StockLocLvl2_Name NVARCHAR(200)  NULL,
    StockLocLvl3_Name NVARCHAR(200)  NULL,
    CONSTRAINT PK_Ref_StockLocation_Master PRIMARY KEY (StockLocId)
);

/* Ref_Uom_Master (62 rows) — units of measure + conversion.  [DATA WE HAVE] */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_Uom_Master] (
    UomId        INT            NOT NULL,   -- PK
    UomName      NVARCHAR(100)  NULL,
    CategoryId   INT            NULL,        -- UoM category (weight/volume/unit)
    Factor       DECIMAL(18,6)  NULL,        -- conversion factor to base
    Rounding     DECIMAL(18,6)  NULL,
    ActiveFlag   BIT            NULL,
    UomType      NVARCHAR(50)   NULL,        -- reference / bigger / smaller
    MeasureType  NVARCHAR(50)   NULL,
    WriteDate    DATETIME2      NULL,
    CreateDate   DATETIME2      NULL,
    LoadDate     DATETIME2      NULL,
    CONSTRAINT PK_Ref_Uom_Master PRIMARY KEY (UomId)
);

/* Ref_StockWarehouse_Master (119 rows) — warehouse + replenishment config.  [DATA WE HAVE]
   (Extract pulled a subset; source also has ManufacturePullId, ReceptionSteps,
   DeliverySteps, Reception/Delivery/Crossdock routes, stock-loc ids — add if needed.) */
CREATE TABLE [HUB_REPORTING_DB].[cfc].[Ref_StockWarehouse_Master] (
    WarehouseId            INT            NOT NULL,   -- PK
    WarehouseName          NVARCHAR(300)  NULL,
    Code                   NVARCHAR(100)  NULL,
    ActiveFlag             BIT            NULL,
    CompanyId              INT            NULL,        -- -> Dim_Company
    PartnerId              INT            NULL,        -- -> Ref_Partner_Master
    BranchId               INT            NULL,        -- -> Ref_Branch_Master (served outlet)
    BuyToResupply          BIT            NULL,        -- replenish by purchase
    ManufactureToResupply  BIT            NULL,        -- replenish by production
    ManuTypeId             INT            NULL,
    Sequence               INT            NULL,
    CONSTRAINT PK_Ref_StockWarehouse_Master PRIMARY KEY (WarehouseId)
);


/* ============================ edm  (FACTS) ============================ */

/* CFC_PBID_Sales_Summary (13,389,442 rows) — ⭐ THE demand fact.  [SOURCE — we extracted an aggregate]
   Grain = DayKey x BranchId x ProductId x CardType. 84 branches, 3,790 products,
   2022-06-21 .. 2026-06-23. Forecast target = net = Quantity - Refund - Void,
   SUMmed over CardType. (Our data/raw/demand_panel.parquet is the GROUP BY of this.) */
CREATE TABLE [HUB_REPORTING_DB].[edm].[CFC_PBID_Sales_Summary] (
    DayKey                          VARCHAR(8)     NOT NULL,   -- 'YYYYMMDD'
    BranchId                        INT            NOT NULL,   -- -> Ref_Branch_Master
    ProductId                       INT            NOT NULL,   -- -> Ref_Product_Master
    CardType                        NVARCHAR(100)  NOT NULL,   -- loyalty/channel (e.g. City Rewards Digital)
    Note                            NVARCHAR(400)  NULL,
    Quantity                        DECIMAL(18,4)  NULL,       -- gross units sold (TARGET basis)
    RefundQuantity                  DECIMAL(18,4)  NULL,
    VoidQuantity                    DECIMAL(18,4)  NULL,
    Amount                          DECIMAL(18,4)  NULL,       -- gross sales value (Ks)
    Discount                        FLOAT          NULL,
    SubTotal                        FLOAT          NULL,       -- net
    PriceTotalAfterLoyaltyDiscount  FLOAT          NULL,       -- post-loyalty net
    TransCount                      INT            NULL,       -- # transactions/receipts
    LoadDate                        DATETIME2      NULL,
    CONSTRAINT PK_CFC_PBID_Sales_Summary
        PRIMARY KEY (DayKey, BranchId, ProductId, CardType)
);

/* CFC_PBID_BranchSales (~86,000 rows) — branch x day sales totals.  [DOC ONLY — cols inferred]
   Fast branch-level baseline (no product grain). */
CREATE TABLE [HUB_REPORTING_DB].[edm].[CFC_PBID_BranchSales] (
    DayKey      VARCHAR(8)     NOT NULL,   -- 'YYYYMMDD'
    BranchId    INT            NOT NULL,   -- -> Ref_Branch_Master
    Quantity    DECIMAL(18,4)  NULL,       -- total units
    Amount      DECIMAL(18,4)  NULL,       -- total sales value
    Discount    FLOAT          NULL,
    TransCount  INT            NULL,
    LoadDate    DATETIME2      NULL,
    CONSTRAINT PK_CFC_PBID_BranchSales PRIMARY KEY (DayKey, BranchId)
);

/* CFC_PBID_SlipDiscount_Summary (~6,700 rows) — discount fact, product x branch x day.  [DOC ONLY — inferred] */
CREATE TABLE [HUB_REPORTING_DB].[edm].[CFC_PBID_SlipDiscount_Summary] (
    DayKey         VARCHAR(8)     NOT NULL,   -- 'YYYYMMDD'
    BranchId       INT            NOT NULL,   -- -> Ref_Branch_Master
    ProductId      INT            NOT NULL,   -- -> Ref_Product_Master
    DiscountAmount FLOAT          NULL,       -- discount value
    Quantity       DECIMAL(18,4)  NULL,       -- discounted units
    TransCount     INT            NULL,
    LoadDate       DATETIME2      NULL,
    CONSTRAINT PK_CFC_PBID_SlipDiscount_Summary
        PRIMARY KEY (DayKey, BranchId, ProductId)
);

/* CFC_PBID_BranchSlipDiscount (~5,200 rows) — discount totals, branch x day.  [DOC ONLY — inferred] */
CREATE TABLE [HUB_REPORTING_DB].[edm].[CFC_PBID_BranchSlipDiscount] (
    DayKey         VARCHAR(8)     NOT NULL,   -- 'YYYYMMDD'
    BranchId       INT            NOT NULL,   -- -> Ref_Branch_Master
    DiscountAmount FLOAT          NULL,
    TransCount     INT            NULL,
    LoadDate       DATETIME2      NULL,
    CONSTRAINT PK_CFC_PBID_BranchSlipDiscount PRIMARY KEY (DayKey, BranchId)
);
