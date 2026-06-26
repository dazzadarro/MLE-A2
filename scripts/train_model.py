from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from utils.model_lifecycle import train_and_select_model


if __name__ == "__main__":
    train_and_select_model(PROJECT_DIR)
