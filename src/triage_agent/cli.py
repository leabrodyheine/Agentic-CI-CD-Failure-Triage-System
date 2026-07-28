"""CLI entry points for the triage agent."""

from __future__ import annotations

import time
from pathlib import Path

import anthropic
import click

from triage_agent.config import ConfigError, Settings
from triage_agent.github_client import GitHubClient
from triage_agent.poller import poll_once, triage_failed_job
from triage_agent.storage import TriageStorage


def _load_settings() -> Settings:
    try:
        return Settings.from_env()
    except ConfigError as exc:
        raise click.ClickException(str(exc))


def _build_clients(settings: Settings) -> tuple[GitHubClient, anthropic.Anthropic]:
    github_client = GitHubClient(token=settings.github_token, repo=settings.github_repo)
    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return github_client, anthropic_client


@click.group()
def main():
    """Agentic CI/CD failure triage system."""


@main.command()
@click.option("--once", is_flag=True, help="Poll a single time instead of looping forever.")
def poll(once: bool):
    """Poll GitHub Actions for new failed runs and triage them."""
    settings = _load_settings()
    github_client, anthropic_client = _build_clients(settings)

    with TriageStorage(settings.db_path) as storage:
        while True:
            records = poll_once(settings, github_client, anthropic_client, storage)
            for record in records:
                click.echo(
                    f"triaged run={record.run.run_id} job={record.run.job_id} "
                    f"category={record.classification.category.value} "
                    f"confidence={record.classification.confidence:.2f} "
                    f"issue={record.issue_url or '(dry-run)'} "
                    f"took={record.total_duration_seconds:.1f}s"
                )
            if once:
                break
            time.sleep(settings.poll_interval_seconds)


@main.command(name="run")
@click.argument("run_id", type=int)
@click.argument("job_id", type=int)
def run_one(run_id: int, job_id: int):
    """Triage a single currently-failing run/job id (for debugging or demos)."""
    settings = _load_settings()
    github_client, anthropic_client = _build_clients(settings)

    runs = {r["id"]: r for r in github_client.list_failed_workflow_runs()}
    if run_id not in runs:
        raise click.ClickException(f"Run {run_id} not found among currently-failed runs.")
    jobs = {j["id"]: j for j in github_client.list_jobs_for_run(run_id)}
    if job_id not in jobs:
        raise click.ClickException(f"Job {job_id} not found on run {run_id}.")

    with TriageStorage(settings.db_path) as storage:
        record = triage_failed_job(
            github_client,
            anthropic_client,
            storage,
            settings.github_repo,
            runs[run_id],
            jobs[job_id],
            dry_run=settings.dry_run,
        )
    click.echo(record.model_dump_json(indent=2))


@main.command(name="eval")
@click.option(
    "--eval-set",
    "eval_set_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a labeled eval set JSON file. Defaults to eval/eval_set.json.",
)
def eval_cmd(eval_set_path: Path | None):
    """Score the classifier against a labeled eval set (see eval/eval_set.json)."""
    from triage_agent.eval_harness import DEFAULT_EVAL_SET_PATH, format_report, run_eval

    settings = _load_settings()
    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    report = run_eval(eval_set_path or DEFAULT_EVAL_SET_PATH, anthropic_client)
    click.echo(format_report(report))


if __name__ == "__main__":
    main()
