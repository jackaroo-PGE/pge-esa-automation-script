-- Run this entire batch in SQL Server Management Studio.
-- Adapted from the September 2026 MAI correction query.
-- Only these two prescriptions are selected, and only NULL ESA_Caltrans values change.
-- "No_original" is the stored value used by the earlier correction.
-- 0 = preview and roll back; 1 = permanently commit.

USE [Constraint];
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @CommitChanges bit = 0;  -- Change to 1 to save the update.
DECLARE @ExpectedUpdates int;
DECLARE @RowsUpdated int;

IF @@TRANCOUNT <> 0
BEGIN
    THROW 50000, 'Run this batch in a session without an existing transaction.', 1;
END;

DECLARE @Targets TABLE
(
    Prescription_Number nvarchar(50) PRIMARY KEY,
    Latitude decimal(12,6),
    Longitude decimal(12,6)
);

INSERT INTO @Targets (Prescription_Number)
VALUES (N'RX-08162548'), (N'RX-08162962');

DECLARE @Changes TABLE
(
    Prescription_Number nvarchar(50),
    ESA_Before nvarchar(255),
    ESA_After nvarchar(255)
);

BEGIN TRY
    BEGIN TRANSACTION;

    -- Require exactly one source record for each prescription.
    IF EXISTS
    (
        SELECT t.Prescription_Number
        FROM @Targets AS t
        LEFT JOIN [dbo].[RPT_PRESCRIPTION] AS rx
            ON rx.pk_s_prescription_name = t.Prescription_Number
        GROUP BY t.Prescription_Number
        HAVING COUNT(rx.pk_s_prescription_name) <> 1
    )
    BEGIN
        THROW 50001, 'Each prescription must match exactly one RPT_PRESCRIPTION record.', 1;
    END;

    -- Obtain the current coordinates; do not reuse the older prescriptions' coordinates.
    UPDATE t
    SET Latitude = TRY_CONVERT(decimal(12,6), rx.n_rx_y6_latitude),
        Longitude = TRY_CONVERT(decimal(12,6), rx.n_rx_x6_longitude)
    FROM @Targets AS t
    JOIN [dbo].[RPT_PRESCRIPTION] AS rx
        ON rx.pk_s_prescription_name = t.Prescription_Number;

    IF EXISTS (SELECT 1 FROM @Targets WHERE Latitude IS NULL OR Longitude IS NULL)
    BEGIN
        THROW 50002, 'A prescription has missing or invalid coordinates. No changes were saved.', 1;
    END;

    IF EXISTS
    (
        SELECT Latitude, Longitude
        FROM @Targets
        GROUP BY Latitude, Longitude
        HAVING COUNT(*) > 1
    )
    BEGIN
        THROW 50003, 'The two prescriptions share the same coordinate key. No changes were saved.', 1;
    END;

    -- Require exactly one MAI row per prescription and lock the matching rows until completion.
    IF EXISTS
    (
        SELECT t.Prescription_Number
        FROM @Targets AS t
        LEFT JOIN [dbo].[MASTER_AGENCY_INTERSECT] AS mai WITH (UPDLOCK, HOLDLOCK)
            ON TRY_CONVERT(decimal(12,6), mai.Y6_LatKey) = t.Latitude
           AND TRY_CONVERT(decimal(12,6), mai.X6_LongKey) = t.Longitude
        GROUP BY t.Prescription_Number
        HAVING COUNT(mai.Y6_LatKey) <> 1
    )
    BEGIN
        THROW 50004, 'Each prescription must match exactly one MASTER_AGENCY_INTERSECT row.', 1;
    END;

    SELECT
        N'Before update' AS Stage,
        t.Prescription_Number,
        t.Latitude,
        t.Longitude,
        mai.ESA_Caltrans
    FROM [dbo].[MASTER_AGENCY_INTERSECT] AS mai
    JOIN @Targets AS t
        ON TRY_CONVERT(decimal(12,6), mai.Y6_LatKey) = t.Latitude
       AND TRY_CONVERT(decimal(12,6), mai.X6_LongKey) = t.Longitude;

    SELECT @ExpectedUpdates = COUNT(*)
    FROM [dbo].[MASTER_AGENCY_INTERSECT] AS mai
    JOIN @Targets AS t
        ON TRY_CONVERT(decimal(12,6), mai.Y6_LatKey) = t.Latitude
       AND TRY_CONVERT(decimal(12,6), mai.X6_LongKey) = t.Longitude
    WHERE mai.ESA_Caltrans IS NULL;

    UPDATE mai
    SET ESA_Caltrans = N'No_original'
    OUTPUT
        t.Prescription_Number,
        deleted.ESA_Caltrans,
        inserted.ESA_Caltrans
    INTO @Changes (Prescription_Number, ESA_Before, ESA_After)
    FROM [dbo].[MASTER_AGENCY_INTERSECT] AS mai
    JOIN @Targets AS t
        ON TRY_CONVERT(decimal(12,6), mai.Y6_LatKey) = t.Latitude
       AND TRY_CONVERT(decimal(12,6), mai.X6_LongKey) = t.Longitude
    WHERE mai.ESA_Caltrans IS NULL;

    SET @RowsUpdated = @@ROWCOUNT;

    IF @RowsUpdated <> @ExpectedUpdates
    BEGIN
        THROW 50005, 'The changed-row count does not match the expected NULL-row count.', 1;
    END;

    IF @CommitChanges = 1
    BEGIN
        COMMIT TRANSACTION;
        SELECT N'COMMITTED: changes permanently saved.' AS Result,
               @RowsUpdated AS Rows_Updated;
    END
    ELSE
    BEGIN
        ROLLBACK TRANSACTION;
        SELECT N'PREVIEW ONLY: changes rolled back. Set @CommitChanges = 1 to save.' AS Result,
               @RowsUpdated AS Rows_That_Would_Update;
    END;

    -- Table variables retain these output rows after the preview rollback.
    SELECT Prescription_Number, ESA_Before, ESA_After
    FROM @Changes
    ORDER BY Prescription_Number;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
