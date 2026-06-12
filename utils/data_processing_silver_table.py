from pathlib import Path
import shutil

import pyspark.sql.functions as F
from pyspark.sql.functions import col
from pyspark.sql.types import DateType, DoubleType, IntegerType, StringType


NUMERIC_COLUMNS = {
    "attributes": ["Age"],
    "financials": [
        "Annual_Income",
        "Monthly_Inhand_Salary",
        "Num_Bank_Accounts",
        "Num_Credit_Card",
        "Interest_Rate",
        "Num_of_Loan",
        "Delay_from_due_date",
        "Num_of_Delayed_Payment",
        "Changed_Credit_Limit",
        "Num_Credit_Inquiries",
        "Outstanding_Debt",
        "Credit_Utilization_Ratio",
        "Total_EMI_per_month",
        "Amount_invested_monthly",
        "Monthly_Balance",
    ],
    "clickstream": [f"fe_{i}" for i in range(1, 21)],
    "lms": [
        "installment_num",
        "tenure",
        "loan_amt",
        "due_amt",
        "paid_amt",
        "overdue_amt",
        "balance",
    ],
}


def _read_bronze(project_dir, table_name, spark):
    path = Path(project_dir) / "datamart" / "bronze" / table_name
    return spark.read.parquet(str(path))


def _write_silver(df, project_dir, table_name, profile=False):
    path = Path(project_dir) / "datamart" / "silver" / table_name
    df.write.mode("overwrite").parquet(str(path))
    message = f"silver/{table_name} -> {path}"
    if profile:
        message = f"{message} ({df.count():,} rows)"
    print(message)
    return df


def _write_audit_log(audit_df, project_dir, profile=False):
    """Write a simple CSV log of Bronze-to-Silver cleaning changes for marking and review."""
    final_path = Path(project_dir) / "datamart" / "silver" / "cleaning_audit_log.csv"
    temp_path = Path(project_dir) / "datamart" / "silver" / "_cleaning_audit_log_tmp"
    if final_path.exists():
        final_path.unlink()
    if temp_path.exists():
        shutil.rmtree(temp_path)

    audit_df.coalesce(1).write.mode("overwrite").option("header", True).csv(str(temp_path))
    part_files = list(temp_path.glob("part-*.csv"))
    if part_files:
        shutil.move(str(part_files[0]), str(final_path))
    shutil.rmtree(temp_path)

    message = f"silver/cleaning_audit_log.csv -> {final_path}"
    if profile:
        message = f"{message} ({audit_df.count():,} rows)"
    print(message)


def _clean_numeric(column_name):
    cleaned = F.regexp_replace(F.trim(col(column_name).cast(StringType())), "[_,]", "")
    cleaned = F.when(cleaned.isin("", "nan", "None", "null"), None).otherwise(cleaned)
    return cleaned.cast(DoubleType())


def _raw_value(column_name):
    return F.trim(col(column_name).cast(StringType()))


def _clean_category(column_name):
    value = F.trim(col(column_name).cast(StringType()))
    return (
        F.when(value.isNull(), None)
        .when(value.isin("", "_", "!@9#%8", "nan", "None", "null"), None)
        .when(F.regexp_replace(value, "_", "") == "", None)
        .otherwise(value)
    )


def _clean_display_category(column_name):
    return F.regexp_replace(_clean_category(column_name), "_", " ")


def _null_if_outside(column_name, min_value, max_value):
    value = col(column_name)
    return F.when(value < min_value, None).when(value > max_value, None).otherwise(value)


def _normalize_loan_type_text(column_name):
    value = _clean_category(column_name)
    value = F.regexp_replace(value, r",\s+and\s+", ", ")
    value = F.regexp_replace(value, r"\s+and\s+", ", ")
    value = F.regexp_replace(value, r"\s*,\s*", ", ")
    return value


def _valid_ssn_or_null(column_name):
    value = _clean_category(column_name)
    return F.when(value.rlike(r"^\d{3}-\d{2}-\d{4}$"), value).otherwise(None)


def _add_raw_columns(df, column_names):
    for column_name in column_names:
        if column_name in df.columns:
            df = df.withColumn(f"__raw_{column_name}", col(column_name).cast(StringType()))
    return df


def _changed_from_raw(column_name):
    original = F.coalesce(col(f"__raw_{column_name}").cast(StringType()), F.lit("__NULL__"))
    cleaned = F.coalesce(col(column_name).cast(StringType()), F.lit("__NULL__"))
    return original != cleaned


def _audit_column(df, table_name, column_name, rationale, condition):
    customer_id = col("Customer_ID").cast(StringType()) if "Customer_ID" in df.columns else F.lit(None).cast(StringType())
    loan_id = col("loan_id").cast(StringType()) if "loan_id" in df.columns else F.lit(None).cast(StringType())
    snapshot_date = (
        col("snapshot_date").cast(StringType()) if "snapshot_date" in df.columns else F.lit(None).cast(StringType())
    )
    return (
        df.filter(condition)
        .select(
            F.lit(table_name).alias("data_file"),
            snapshot_date.alias("snapshot_date"),
            customer_id.alias("Customer_ID"),
            loan_id.alias("loan_id"),
            F.lit(column_name).alias("column_name"),
            F.coalesce(col(f"__raw_{column_name}").cast(StringType()), F.lit("NULL")).alias("original_value"),
            F.coalesce(col(column_name).cast(StringType()), F.lit("NULL")).alias("changed_to"),
            F.lit(rationale).alias("rationale"),
        )
    )


def _union_audits(audit_frames):
    audit_frames = [audit_df for audit_df in audit_frames if audit_df is not None]
    if not audit_frames:
        return None
    combined = audit_frames[0]
    for audit_df in audit_frames[1:]:
        combined = combined.unionByName(audit_df)
    return combined


def _cast_numeric_columns(df, table_name):
    for column_name in NUMERIC_COLUMNS[table_name]:
        df = df.withColumn(column_name, _clean_numeric(column_name))
    return df


def build_silver_tables(project_dir, spark, profile=False):
    """Clean and conform the four source domains without creating ML-ready stores."""
    # Silver responsibilities: schema enforcement, cleanup, and key conformance.
    # Model-specific feature engineering, encoding, and scaling are deferred to Gold to avoid leakage.

    audit_frames = []

    attributes = _read_bronze(project_dir, "attributes", spark)
    attributes = _add_raw_columns(attributes, ["Customer_ID", "snapshot_date", "Name", "Age", "SSN", "Occupation"])
    attributes = (
        attributes.withColumn("Customer_ID", _clean_category("Customer_ID"))
        .withColumn("snapshot_date", F.to_date(col("snapshot_date")))
        .withColumn("Name", _clean_category("Name"))
        # SSN is an identifier, not a model feature. Invalid formats are nulled, not imputed.
        .withColumn("SSN", _valid_ssn_or_null("SSN"))
        .withColumn("Occupation", _clean_display_category("Occupation"))
    )
    attributes = _cast_numeric_columns(attributes, "attributes")
    # Impossible demographic values are set to null in Silver; Gold handles train-only imputation.
    attributes = attributes.withColumn("Age", _null_if_outside("Age", 18, 100).cast(IntegerType()))
    audit_frames.extend(
        [
            _audit_column(
                attributes,
                "attributes",
                "Age",
                "Set to null because Age is outside the valid 18-100 range.",
                col("__raw_Age").isNotNull() & col("Age").isNull(),
            ),
            _audit_column(
                attributes,
                "attributes",
                "SSN",
                "Set to null because SSN does not match ###-##-####.",
                col("__raw_SSN").isNotNull() & col("SSN").isNull(),
            ),
            _audit_column(
                attributes,
                "attributes",
                "Occupation",
                "Cleaned placeholder values and normalized underscores for readability.",
                _changed_from_raw("Occupation"),
            ),
        ]
    )
    attributes = (
        attributes.filter(col("Customer_ID").isNotNull() & col("snapshot_date").isNotNull())
        .select("Customer_ID", "Name", "Age", "SSN", "Occupation", "snapshot_date")
        .dropDuplicates(["Customer_ID", "snapshot_date"])
    )
    _write_silver(attributes, project_dir, "attributes", profile)

    financials = _read_bronze(project_dir, "financials", spark)
    financials = _add_raw_columns(
        financials,
        [
            "Customer_ID",
            "snapshot_date",
            "Type_of_Loan",
            "Credit_Mix",
            "Credit_History_Age",
            "Payment_of_Min_Amount",
            "Payment_Behaviour",
            "Num_Bank_Accounts",
            "Num_Credit_Card",
            "Interest_Rate",
            "Num_of_Loan",
            "Num_of_Delayed_Payment",
        ],
    )
    financials = (
        financials.withColumn("Customer_ID", _clean_category("Customer_ID"))
        .withColumn("snapshot_date", F.to_date(col("snapshot_date")))
        .withColumn("Type_of_Loan", _normalize_loan_type_text("Type_of_Loan"))
        .withColumn("Credit_Mix", _clean_category("Credit_Mix"))
        .withColumn("Credit_History_Age", _clean_category("Credit_History_Age"))
        .withColumn("Payment_of_Min_Amount", _clean_category("Payment_of_Min_Amount"))
        .withColumn("Payment_Behaviour", _clean_category("Payment_Behaviour"))
    )
    financials = _cast_numeric_columns(financials, "financials")
    # Deterministic domain rules remove impossible source values without learning from the dataset.
    # Rows are retained because other columns in the same customer snapshot may still be useful.
    financials = (
        financials.withColumn("Num_Bank_Accounts", _null_if_outside("Num_Bank_Accounts", 0, 50))
        .withColumn("Num_Credit_Card", _null_if_outside("Num_Credit_Card", 0, 100))
        .withColumn("Interest_Rate", _null_if_outside("Interest_Rate", 0, 100))
        .withColumn("Num_of_Loan", _null_if_outside("Num_of_Loan", 0, 100))
        .withColumn("Num_of_Delayed_Payment", _null_if_outside("Num_of_Delayed_Payment", 0, 100))
    )
    audit_frames.extend(
        [
            _audit_column(
                financials,
                "financials",
                "Type_of_Loan",
                "Normalized loan type delimiters by replacing 'and' connectors with commas.",
                _changed_from_raw("Type_of_Loan"),
            ),
            _audit_column(
                financials,
                "financials",
                "Credit_Mix",
                "Cleaned blank, placeholder, or invalid category values.",
                _changed_from_raw("Credit_Mix"),
            ),
            _audit_column(
                financials,
                "financials",
                "Payment_of_Min_Amount",
                "Cleaned blank, placeholder, or invalid category values.",
                _changed_from_raw("Payment_of_Min_Amount"),
            ),
            _audit_column(
                financials,
                "financials",
                "Payment_Behaviour",
                "Cleaned blank, placeholder, or invalid category values.",
                _changed_from_raw("Payment_Behaviour"),
            ),
            _audit_column(
                financials,
                "financials",
                "Num_Bank_Accounts",
                "Set to null because bank account count is outside the valid 0-50 range.",
                col("__raw_Num_Bank_Accounts").isNotNull() & col("Num_Bank_Accounts").isNull(),
            ),
            _audit_column(
                financials,
                "financials",
                "Num_Credit_Card",
                "Set to null because credit card count is outside the valid 0-100 range.",
                col("__raw_Num_Credit_Card").isNotNull() & col("Num_Credit_Card").isNull(),
            ),
            _audit_column(
                financials,
                "financials",
                "Interest_Rate",
                "Set to null because interest rate is outside the valid 0-100 percent range.",
                col("__raw_Interest_Rate").isNotNull() & col("Interest_Rate").isNull(),
            ),
            _audit_column(
                financials,
                "financials",
                "Num_of_Loan",
                "Set to null because loan count is outside the valid 0-100 range.",
                col("__raw_Num_of_Loan").isNotNull() & col("Num_of_Loan").isNull(),
            ),
            _audit_column(
                financials,
                "financials",
                "Num_of_Delayed_Payment",
                "Set to null because delayed payment count is outside the valid 0-100 range.",
                col("__raw_Num_of_Delayed_Payment").isNotNull() & col("Num_of_Delayed_Payment").isNull(),
            ),
        ]
    )
    financials = (
        financials.filter(col("Customer_ID").isNotNull() & col("snapshot_date").isNotNull())
        .drop(*[column_name for column_name in financials.columns if column_name.startswith("__raw_")])
        .dropDuplicates(["Customer_ID", "snapshot_date"])
    )
    _write_silver(financials, project_dir, "financials", profile)

    clickstream = _read_bronze(project_dir, "clickstream", spark)
    clickstream = _add_raw_columns(clickstream, ["Customer_ID", "snapshot_date"])
    clickstream = (
        clickstream.withColumn("Customer_ID", _clean_category("Customer_ID"))
        .withColumn("snapshot_date", F.to_date(col("snapshot_date")))
    )
    clickstream = _cast_numeric_columns(clickstream, "clickstream")
    clickstream = (
        clickstream.filter(col("Customer_ID").isNotNull() & col("snapshot_date").isNotNull())
        .drop(*[column_name for column_name in clickstream.columns if column_name.startswith("__raw_")])
    )
    # Clickstream may contain multiple events per Customer_ID + snapshot_date, so uniqueness is checked after Gold aggregation.
    _write_silver(clickstream, project_dir, "clickstream", profile)

    lms = _read_bronze(project_dir, "lms", spark)
    lms = _add_raw_columns(lms, ["loan_id", "Customer_ID", "snapshot_date", "loan_start_date"])
    lms = (
        lms.withColumn("loan_id", _clean_category("loan_id"))
        .withColumn("Customer_ID", _clean_category("Customer_ID"))
        .withColumn("loan_start_date", F.to_date(col("loan_start_date")))
        .withColumn("snapshot_date", F.to_date(col("snapshot_date")))
    )
    lms = _cast_numeric_columns(lms, "lms")
    lms = (
        lms.withColumn("installment_num", col("installment_num").cast(IntegerType()))
        .withColumn("tenure", col("tenure").cast(IntegerType()))
        .filter(col("loan_id").isNotNull() & col("Customer_ID").isNotNull() & col("snapshot_date").isNotNull())
        .drop(*[column_name for column_name in lms.columns if column_name.startswith("__raw_")])
        .dropDuplicates(["loan_id", "installment_num", "snapshot_date"])
    )
    _write_silver(lms, project_dir, "lms", profile)

    audit_log = _union_audits(audit_frames)
    if audit_log is not None:
        _write_audit_log(audit_log, project_dir, profile)

    return {
        "attributes": attributes,
        "financials": financials,
        "clickstream": clickstream,
        "lms": lms,
    }
