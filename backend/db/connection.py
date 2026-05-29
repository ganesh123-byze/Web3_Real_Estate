import logging

from psycopg2 import connect
from psycopg2.extras import RealDictCursor

from backend.config.settings import get_database_url, is_managed_postgres_url

LOGGER = logging.getLogger(__name__)


class PostgreSQLConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self, dictionary: bool = False):
        if dictionary:
            return self._connection.cursor(cursor_factory=RealDictCursor)
        return self._connection.cursor()

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_connection():
    url = get_database_url()
    if is_managed_postgres_url(url) and "pooler" in url.lower():
        LOGGER.debug(
            "DATABASE_URL uses a pooler host; if DDL fails, use Neon's direct connection string in .env"
        )
    return PostgreSQLConnection(
        connect(
            url,
            connect_timeout=30,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
    )
