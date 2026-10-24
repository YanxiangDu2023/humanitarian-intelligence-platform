from dataclasses import dataclass

from psycopg import Connection


@dataclass(frozen=True)
class QualityResult:
    total_checks: int
    passed_checks: int
    missing_checks: int
    out_of_range_checks: int

    @property
    def is_valid(self) -> bool:
        return self.missing_checks == 0 and self.out_of_range_checks == 0


def validate_database(connection: Connection) -> QualityResult:
    rows = connection.execute(
        """
        SELECT quality_status, COUNT(*)
        FROM quality.country_indicator_checks
        GROUP BY quality_status
        """
    ).fetchall()
    counts = {str(status): int(count) for status, count in rows}
    return QualityResult(
        total_checks=sum(counts.values()),
        passed_checks=counts.get("pass", 0),
        missing_checks=counts.get("missing", 0),
        out_of_range_checks=counts.get("out_of_range", 0),
    )
