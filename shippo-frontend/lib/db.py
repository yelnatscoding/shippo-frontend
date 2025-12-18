"""
Database helper for Vercel Postgres
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager


@contextmanager
def get_db_connection():
    """Get database connection from Vercel Postgres environment variables"""
    conn = psycopg2.connect(os.environ['POSTGRES_URL'])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS label_history (
                    id SERIAL PRIMARY KEY,
                    tracking_number VARCHAR(255) NOT NULL,
                    carrier VARCHAR(100) NOT NULL,
                    service VARCHAR(255),
                    cost DECIMAL(10, 2),
                    currency VARCHAR(10) DEFAULT 'USD',
                    provider VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    from_address JSONB,
                    to_address JSONB,
                    google_drive_link TEXT,
                    google_drive_file_id VARCHAR(255),
                    signature_confirmation VARCHAR(50),
                    label_id VARCHAR(255),
                    label_download_url TEXT,
                    voided BOOLEAN DEFAULT FALSE
                );

                CREATE INDEX IF NOT EXISTS idx_tracking_number ON label_history(tracking_number);
                CREATE INDEX IF NOT EXISTS idx_created_at ON label_history(created_at DESC);
            """)


def add_label(label_data):
    """Add a label to history"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO label_history (
                    tracking_number, carrier, service, cost, currency,
                    provider, created_at, from_address, to_address,
                    google_drive_link, google_drive_file_id, signature_confirmation,
                    label_id, label_download_url
                ) VALUES (
                    %(tracking_number)s, %(carrier)s, %(service)s, %(cost)s, %(currency)s,
                    %(provider)s, %(created_at)s, %(from_address)s, %(to_address)s,
                    %(google_drive_link)s, %(google_drive_file_id)s, %(signature_confirmation)s,
                    %(label_id)s, %(label_download_url)s
                )
                RETURNING *
            """, label_data)
            return dict(cur.fetchone())


def get_labels(limit=100, offset=0, from_date=None, to_date=None):
    """Get label history with optional filters"""
    import json

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM label_history WHERE 1=1"
            params = {'limit': limit, 'offset': offset}

            if from_date:
                query += " AND created_at >= %(from_date)s"
                params['from_date'] = from_date

            if to_date:
                query += " AND created_at <= %(to_date)s"
                params['to_date'] = to_date

            query += " ORDER BY created_at DESC LIMIT %(limit)s OFFSET %(offset)s"

            cur.execute(query, params)
            results = []
            for row in cur.fetchall():
                label = dict(row)
                # Parse JSON strings back to objects for frontend
                if label.get('from_address') and isinstance(label['from_address'], str):
                    try:
                        label['from_address'] = json.loads(label['from_address'])
                    except:
                        pass
                if label.get('to_address') and isinstance(label['to_address'], str):
                    try:
                        label['to_address'] = json.loads(label['to_address'])
                    except:
                        pass
                results.append(label)
            return results


def get_label_count(from_date=None, to_date=None):
    """Get total count of labels"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = "SELECT COUNT(*) FROM label_history WHERE 1=1"
            params = {}

            if from_date:
                query += " AND created_at >= %(from_date)s"
                params['from_date'] = from_date

            if to_date:
                query += " AND created_at <= %(to_date)s"
                params['to_date'] = to_date

            cur.execute(query, params)
            return cur.fetchone()[0]
