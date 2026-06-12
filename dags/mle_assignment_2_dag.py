from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


PROJECT_DIR = "/opt/airflow/project"
PYTHON = "PYTHONPATH=. python"

default_args = {
    "owner": "darren",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="mle_assignment_2_pipeline",
    description="Backfillable loan-default training, inference and monitoring pipeline",
    schedule="0 0 1 * *",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2024, 12, 1),
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
    tags=["CS611", "loan-default", "monitoring"],
) as dag:
    start = EmptyOperator(task_id="start")

    prepare_medallion = BashOperator(
        task_id="prepare_bronze_silver_gold",
        bash_command=f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_medallion.py --snapshotdate '{{{{ ds }}}}'",
    )

    select_champion = BashOperator(
        task_id="train_or_load_champion",
        bash_command=f"cd '{PROJECT_DIR}' && {PYTHON} scripts/ensure_champion.py",
    )

    monthly_inference = BashOperator(
        task_id="monthly_batch_inference",
        bash_command=f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_inference.py --snapshotdate '{{{{ ds }}}}'",
    )

    monthly_monitoring = BashOperator(
        task_id="monitor_p0_p1_psi_csi",
        bash_command=f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_monitoring.py --snapshotdate '{{{{ ds }}}}'",
    )

    completed = EmptyOperator(task_id="completed")

    start >> prepare_medallion >> select_champion >> monthly_inference >> monthly_monitoring >> completed
