from pathlib import Path

from pyspark.sql.types import StringType, StructField, StructType


RAW_TABLES = {
    "attributes": "features_attributes.csv",
    "financials": "features_financials.csv",
    "clickstream": "feature_clickstream.csv",
    "lms": "lms_loan_daily.csv",
}


EXPECTED_COLUMNS = {
    "attributes": [
        "Customer_ID",
        "Name",
        "Age",
        "SSN",
        "Occupation",
        "snapshot_date",
    ],
    "financials": [
        "Customer_ID",
        "Annual_Income",
        "Monthly_Inhand_Salary",
        "Num_Bank_Accounts",
        "Num_Credit_Card",
        "Interest_Rate",
        "Num_of_Loan",
        "Type_of_Loan",
        "Delay_from_due_date",
        "Num_of_Delayed_Payment",
        "Changed_Credit_Limit",
        "Num_Credit_Inquiries",
        "Credit_Mix",
        "Outstanding_Debt",
        "Credit_Utilization_Ratio",
        "Credit_History_Age",
        "Payment_of_Min_Amount",
        "Total_EMI_per_month",
        "Amount_invested_monthly",
        "Payment_Behaviour",
        "Monthly_Balance",
        "snapshot_date",
    ],
    "clickstream": [
        *[f"fe_{i}" for i in range(1, 21)],
        "Customer_ID",
        "snapshot_date",
    ],
    "lms": [
        "loan_id",
        "Customer_ID",
        "loan_start_date",
        "tenure",
        "installment_num",
        "loan_amt",
        "due_amt",
        "paid_amt",
        "overdue_amt",
        "balance",
        "snapshot_date",
    ],
}


def _validate_columns(table_name, actual_columns):
    missing_columns = [column for column in EXPECTED_COLUMNS[table_name] if column not in actual_columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{table_name} is missing required source columns: {missing}")


def _read_raw_csv_as_strings(source_path, table_name, spark):
    header_df = spark.read.option("header", True).option("inferSchema", False).csv(str(source_path)).limit(0)
    _validate_columns(table_name, header_df.columns)

    # Bronze keeps raw-like values. Reading as StringType avoids accidental business cleaning or type coercion.
    schema = StructType([StructField(column, StringType(), True) for column in header_df.columns])
    return spark.read.option("header", True).schema(schema).csv(str(source_path))


def build_bronze_tables(project_dir, spark, profile=False):
    """Ingest raw CSV files into source-domain Bronze parquet tables."""
    project_dir = Path(project_dir)
    bronze_root = project_dir / "datamart" / "bronze"

    bronze_paths = {}
    for table_name, filename in RAW_TABLES.items():
        source_path = project_dir / "data" / filename
        output_path = bronze_root / table_name

        df = _read_raw_csv_as_strings(source_path, table_name, spark)

        # Bronze is partitioned for efficient downstream reads, but business values are left untouched.
        df.write.mode("overwrite").partitionBy("snapshot_date").parquet(str(output_path))

        bronze_paths[table_name] = output_path
        message = f"bronze/{table_name} -> {output_path}"
        if profile:
            message = f"{message} ({df.count():,} rows)"
        print(message)

    return bronze_paths
