import argparse
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from utils.model_lifecycle import calculate_monthly_monitoring


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", default=None)
    args = parser.parse_args()
    calculate_monthly_monitoring(PROJECT_DIR, args.snapshotdate)
