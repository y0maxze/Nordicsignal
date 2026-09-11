from psycopg.pq import TransactionStatus

from database import PostgresConnection


class _Info:
    def __init__(self, status):
        self.transaction_status = status


class _RawConnection:
    def __init__(self, status):
        self.info = _Info(status)
        self.rollback_calls = 0
        self.close_calls = 0

    def rollback(self):
        self.rollback_calls += 1
        self.info.transaction_status = TransactionStatus.IDLE

    def close(self):
        self.close_calls += 1


class _Pool:
    def __init__(self):
        self.returned = []

    def putconn(self, connection):
        self.returned.append(connection)


def test_close_rolls_back_open_transaction_before_pool_return():
    raw = _RawConnection(TransactionStatus.INTRANS)
    pool = _Pool()
    conn = PostgresConnection(raw, pool=pool)

    conn.close()

    assert raw.rollback_calls == 1
    assert pool.returned == [raw]
    assert raw.info.transaction_status == TransactionStatus.IDLE


def test_close_rolls_back_failed_transaction_before_pool_return():
    raw = _RawConnection(TransactionStatus.INERROR)
    pool = _Pool()
    conn = PostgresConnection(raw, pool=pool)

    conn.close()

    assert raw.rollback_calls == 1
    assert pool.returned == [raw]


def test_close_does_not_rollback_idle_connection():
    raw = _RawConnection(TransactionStatus.IDLE)
    pool = _Pool()
    conn = PostgresConnection(raw, pool=pool)

    conn.close()
    conn.close()

    assert raw.rollback_calls == 0
    assert pool.returned == [raw]


def test_non_pooled_connection_keeps_direct_close_behavior():
    raw = _RawConnection(TransactionStatus.INTRANS)
    conn = PostgresConnection(raw)

    conn.close()

    assert raw.rollback_calls == 0
    assert raw.close_calls == 1
