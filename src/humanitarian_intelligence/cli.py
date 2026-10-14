import argparse

from humanitarian_intelligence.config import get_settings
from humanitarian_intelligence.db import connect, initialize_database
from humanitarian_intelligence.etl.unicef import run_pipeline as run_unicef_pipeline
from humanitarian_intelligence.etl.world_bank import run_pipeline
from humanitarian_intelligence.quality import validate_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Humanitarian Intelligence data pipelines")
    parser.add_argument(
        "command",
        choices=("init-db", "world-bank", "unicef", "validate"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()

    with connect(settings.database_url) as connection:
        if args.command == "init-db":
            initialize_database(connection)
            print("Database schemas and tables initialized.")
            return

        if args.command == "validate":
            result = validate_database(connection)
            print(
                "Data quality checks: "
                f"{result.passed_checks}/{result.total_checks} passed, "
                f"{result.missing_checks} missing, "
                f"{result.out_of_range_checks} out of range."
            )
            if not result.is_valid:
                raise SystemExit(1)
            return

        if args.command == "world-bank":
            run_id = run_pipeline(
                connection=connection,
                countries=settings.countries,
                indicators=settings.indicators,
                start_year=settings.world_bank_start_year,
                end_year=settings.world_bank_end_year,
                timeout_seconds=settings.http_timeout_seconds,
            )
            print(f"World Bank pipeline completed: {run_id}")
            return

        run_id = run_unicef_pipeline(
            connection=connection,
            countries=settings.countries,
            indicators=settings.unicef_indicator_codes,
            start_year=settings.unicef_start_year,
            end_year=settings.unicef_end_year,
            timeout_seconds=settings.http_timeout_seconds,
        )
        print(f"UNICEF pipeline completed: {run_id}")


if __name__ == "__main__":
    main()

