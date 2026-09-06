"""
loadshedding_pipeline_dag.py

Orchestrates the EXISTING extract -> transform -> load pipeline on a
schedule. This DAG does not reimplement any pipeline logic - it runs
the exact same scripts already built, tested, and used both directly
and via `docker compose run` (see docker-compose.yml). Airflow's only
job here is scheduling, dependency ordering, retries, and visibility
into whether each run succeeded - not the data processing itself.

Design decision: BashOperator, not PythonOperator. Each script already
has a clean CLI entrypoint that returns a proper exit code (0 success,
1 failure) - see main() in each script. BashOperator automatically
marks a task as failed when the underlying command exits non-zero,
which means the exit-code discipline already built into every stage of
this pipeline plugs directly into Airflow's own success/failure
tracking with no extra glue code.
"""

from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

default_args = {
    "owner": "njabulo",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="loadshedding_pipeline",
    description="Extract, validate, and load SA load shedding data on a schedule",
    default_args=default_args,
    # Hourly = 24 calls/day against EskomSePush's free tier, comfortably
    # under the 50/day quota with room for manual testing on top.
    schedule="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["loadshedding", "data-engineering"],
) as dag:

    extract = BashOperator(
        task_id="extract",
        bash_command="python /opt/airflow/pipeline/extractor/extract.py",
    )

    transform = BashOperator(
        task_id="transform",
        bash_command="python /opt/airflow/pipeline/transform/transform.py",
    )

    load = BashOperator(
        task_id="load",
        bash_command="python /opt/airflow/pipeline/loader/load.py",
    )

    # The actual dependency graph: transform can't run until extract has
    # produced a new raw file, and load can't run until transform has
    # produced validated output. Matches exactly the manual sequence
    # used throughout this project.
    extract >> transform >> load
