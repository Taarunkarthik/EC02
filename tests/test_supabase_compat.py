from database import normalize_database_url, prepare_compat_sql


def test_normalize_database_url_converts_supabase_uri():
    raw = "postgres://postgres:secret@aws-0-region.pooler.supabase.com:6543/postgres"
    expected = "postgresql://postgres:secret@aws-0-region.pooler.supabase.com:6543/postgres"
    assert normalize_database_url(raw) == expected


def test_prepare_compat_sql_rewrites_sqlite_only_statements():
    insert_sql = "INSERT OR IGNORE INTO competition_controls (id, generation) VALUES (?, ?)"
    assert prepare_compat_sql(insert_sql) == (
        "INSERT INTO competition_controls (id, generation) VALUES (%s, %s) ON CONFLICT DO NOTHING"
    )

    begin_sql = "BEGIN IMMEDIATE"
    assert prepare_compat_sql(begin_sql) == "BEGIN"

    dashboard_sql = """
        SELECT GROUP_CONCAT(name, ', ') AS members
        FROM participants
        WHERE created_at >= datetime('now', '-5 minutes')
    """
    normalized = prepare_compat_sql(dashboard_sql)
    assert "STRING_AGG(name, ', ')" in normalized
    assert "CURRENT_TIMESTAMP - INTERVAL '-5 minutes'" in normalized
    assert prepare_compat_sql("UPDATE participant_security SET violations = MIN(violations + 1, ?)") == (
        "UPDATE participant_security SET violations = LEAST(violations + 1, %s)"
    )
