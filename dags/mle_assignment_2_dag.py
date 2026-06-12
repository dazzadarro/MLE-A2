from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


PROJECT_DIR = "/opt/airflow/project"
PYTHON = "PYTHONPATH=. python"
MANUAL_SNAPSHOT_DATE = "{{ dag_run.conf.get('snapshotdate', '2025-01-01') }}"
BACKFILL_SNAPSHOT_DATE = "{{ ds }}"

default_args = {
    "owner": "darren",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def build_pipeline_dag(
    dag_id,
    snapshot_date,
    schedule,
    catchup,
    start_date,
    end_date=None,
    paused=False,
):
    dag = DAG(
        dag_id=dag_id,
        description="Loan-default training, inference and monitoring pipeline",
        schedule=schedule,
        start_date=start_date,
        end_date=end_date,
        catchup=catchup,
        max_active_runs=1,
        default_args=default_args,
        is_paused_upon_creation=paused,
        tags=["CS611", "loan-default", "monitoring"],
    )

    with dag:
        start = EmptyOperator(task_id="start")

        prepare_medallion = BashOperator(
            task_id="prepare_bronze_silver_gold",
            bash_command=(
                f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_medallion.py "
                f"--snapshotdate '{snapshot_date}'"
            ),
        )

        select_champion = BashOperator(
            task_id="train_or_load_champion",
            bash_command=f"cd '{PROJECT_DIR}' && {PYTHON} scripts/ensure_champion.py",
        )

        monthly_inference = BashOperator(
            task_id="monthly_batch_inference",
            bash_command=(
                f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_inference.py "
                f"--snapshotdate '{snapshot_date}'"
            ),
        )

        monthly_monitoring = BashOperator(
            task_id="monitor_p0_p1_psi_csi",
            bash_command=(
                f"cd '{PROJECT_DIR}' && {PYTHON} scripts/run_monitoring.py "
                f"--snapshotdate '{snapshot_date}'"
            ),
        )

        completed = EmptyOperator(task_id="completed")
        (
            start
            >> prepare_medallion
            >> select_champion
            >> monthly_inference
            >> monthly_monitoring
            >> completed
        )

    return dag


# Marker-friendly entry point. Clicking "Trigger DAG" runs the latest OOT month
# without requiring configuration; another month can be supplied in dag_run.conf.
mle_assignment_2_pipeline = build_pipeline_dag(
    dag_id="mle_assignment_2_pipeline",
    snapshot_date=MANUAL_SNAPSHOT_DATE,
    schedule=None,
    catchup=False,
    start_date=datetime(2023, 1, 1),
)

# Historical monthly orchestration is kept separately so its catchup runs do
# not block or confuse the marker's manual end-to-end test.
mle_assignment_2_monthly_backfill = build_pipeline_dag(
    dag_id="mle_assignment_2_monthly_backfill",
    snapshot_date=BACKFILL_SNAPSHOT_DATE,
    schedule="0 0 1 * *",
    catchup=True,
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2025, 1, 1),
    paused=True,
)
