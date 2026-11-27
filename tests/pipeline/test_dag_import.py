"""Import and structural verification tests for Airflow 3.x DAG definitions."""

from pipeline.dags import zomato_weekly_etl


def test_zomato_weekly_etl_dag_structure() -> None:
    dag = zomato_weekly_etl.dag_instance
    assert dag.dag_id == "zomato_weekly_etl"
    assert dag.schedule == "@weekly"
    assert dag.catchup is False
    assert dag.max_active_runs == 1

    expected_tasks = [
        "check_zomato_version",
        "fetch_and_store_bronze",
        "standardize_and_validate_silver",
        "enforce_quality_gate",
        "upsert_silver",
        "refresh_gold",
        "record_pipeline_run_summary",
    ]
    for task_id in expected_tasks:
        assert task_id in dag.task_ids

    summary_task = dag.get_task("record_pipeline_run_summary")
    assert summary_task.trigger_rule == "all_done"
    assert "check_zomato_version" in summary_task.upstream_task_ids
    assert "refresh_gold" in summary_task.upstream_task_ids
