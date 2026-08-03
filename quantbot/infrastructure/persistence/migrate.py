# quantbot/infrastructure/persistence/migrate.py
"""依序套用 migrations/ 底下的 .sql，套用過的跳過。

uv run python -m quantbot.infrastructure.persistence.migrate
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from quantbot.infrastructure.persistence.postgres_database import PostgresDatabase


class SqlMigrationRunner:
    """用 schema_migrations 記錄套用過哪些檔案，跑第二次不會重複執行。

    每一句 SQL 分開送，NEVER 把整個檔案當一句：CREATE MATERIALIZED VIEW
    ... WITH (timescaledb.continuous) 與 CALL refresh_continuous_aggregate()
    都不能在交易區塊裡跑，而多句一起送會被 Postgres 包成隱式交易。
    代價是一個檔案跑到一半失敗不會整份回滾，所以每一句都要能重跑
    （IF NOT EXISTS / if_not_exists => TRUE）。
    """

    TRACKING_DDL = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        filename   TEXT        NOT NULL PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """

    def __init__(self, database: PostgresDatabase, *, directory: Path) -> None:
        self._database = database
        self._directory = directory

    async def run(self) -> list[str]:
        """套用還沒套用過的檔案，回傳這次實際跑了哪些。"""
        pool = await self._database.pool()
        async with pool.acquire() as connection:
            await connection.execute(self.TRACKING_DDL)
            applied = {
                row["filename"]
                for row in await connection.fetch(
                    "SELECT filename FROM schema_migrations"
                )
            }

            freshly_applied: list[str] = []
            for path in sorted(self._directory.glob("*.sql")):
                if path.name in applied:
                    continue
                for statement in self.statements(path.read_text(encoding="utf-8")):
                    await connection.execute(statement)
                await connection.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", path.name
                )
                freshly_applied.append(path.name)
            return freshly_applied

    @staticmethod
    def statements(sql: str) -> list[str]:
        """把一份 .sql 拆成一句一句。

        只處理這個專案自己寫的 migration：拿掉 -- 註解，再以分號切開。
        這些 SQL 裡沒有字串字面值或函式本體帶分號，所以夠用；
        要支援任意 SQL 的話該換成真正的 parser。
        """
        stripped = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
        return [
            statement.strip() for statement in stripped.split(";") if statement.strip()
        ]


async def main() -> int:
    directory = Path(__file__).parent / "migrations"
    runner = SqlMigrationRunner(PostgresDatabase.from_settings(), directory=directory)
    applied = await runner.run()

    if applied:
        for filename in applied:
            print(f"套用 {filename}")
    else:
        print("沒有待套用的 migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
