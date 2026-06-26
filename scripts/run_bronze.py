import argparse
from pathlib import Path
import sys

import pyspark

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from utils.data_processing_bronze_table import build_bronze_tables


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
        PROJECT_DIR / "datamart" / "bronze" / "attributes",
        PROJECT_DIR / "datamart" / "bronze" / "financials",
        PROJECT_DIR / "datamart" / "bronze" / "clickstream",
        PROJECT_DIR / "datamart" / "bronze" / "lms",
    ]
    if not args.force and all(path.exists() for path in required_outputs):
        print("Bronze tables already exist; Bronze rebuild skipped.")
        return

    spark = spark_session("mle_a2_bronze")
    spark.sparkContext.setLogLevel("ERROR")
    try:
        build_bronze_tables(PROJECT_DIR, spark)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
