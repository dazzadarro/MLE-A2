from pathlib import Path

from utils.model_lifecycle import train_and_select_model


if __name__ == "__main__":
    train_and_select_model(Path(__file__).resolve().parents[1])
