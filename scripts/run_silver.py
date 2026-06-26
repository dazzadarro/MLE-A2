import argparse
from pathlib import Path
import sys

import pyspark

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from utils.data_processing_silver_table import build_silver_tables


def spark_session(app_name):
    return (
        pyspark.sql.SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    required_outputs = [
        PROJECT_DIR / "datamart" / "silver" / "attributes",
        PROJECT_DIR / "datamart" / "silver" / "financials",
        PROJECT_DIR / "datamart" / "silver" / "clickstream",
        PROJECT_DIR / "datamart" / "silver" / "lms",
    ]
    if not args.force and all(path.exists() for path in required_outputs):
        print("Silver tables already exist; Silver rebuild skipped.")
        return

    spark = spark_session("mle_a2_silver")
    spark.sparkContext.setLogLevel("ERROR")
    try:
        build_silver_tables(PROJECT_DIR, spark)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
