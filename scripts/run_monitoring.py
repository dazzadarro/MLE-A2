import argparse
from pathlib import Path

from utils.model_lifecycle import calculate_monthly_monitoring


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", required=True)
    args = parser.parse_args()
    calculate_monthly_monitoring(Path(__file__).resolve().parents[1], args.snapshotdate)
