"""Persistent outbox for one bridge process and one cloud destination."""
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path


class UploadQueue:
    def __init__(self, path, url, key, capacity=1000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.url, self.key, self.capacity = url, key, capacity
        self.lock = threading.RLock()
        with closing(self.connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, destination TEXT NOT NULL,
                instrument TEXT NOT NULL, record TEXT NOT NULL,
                payload TEXT NOT NULL, rejected INTEGER,
                UNIQUE(destination, instrument, record)
            )""")

    def connect(self):
        return sqlite3.connect(self.path)

    def enqueue(self, record):
        payload = json.dumps(record, sort_keys=True, allow_nan=False)
        identity = (self.url, record['instrument_id'], record['id'])
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute(
                'SELECT seq, payload FROM outbox WHERE destination=? AND instrument=? AND record=?',
                identity,
            ).fetchone()
            if row:
                if row[1] != payload:
                    raise ValueError('Conflicting payload for queued record')
                return row[0]
            if db.execute('SELECT count(*) FROM outbox').fetchone()[0] >= self.capacity:
                raise OverflowError('Upload queue is full')
            return db.execute(
                'INSERT INTO outbox(destination,instrument,record,payload) VALUES (?,?,?,?)',
                (*identity, payload),
            ).lastrowid

    def send(self, seq=None):
        """Attempt one pending row. Return true only after a successful upload."""
        with self.lock, closing(self.connect()) as db:
            query = 'SELECT seq,payload FROM outbox WHERE destination=? AND rejected IS NULL'
            args = (self.url,)
            if seq is not None:
                query += ' AND seq=?'
                args += (seq,)
            row = db.execute(query + ' ORDER BY seq LIMIT 1', args).fetchone()
            if row is None:
                return False
            request = urllib.request.Request(
                self.url, data=row[1].encode(), method='POST',
                headers={'Content-Type': 'application/json', 'X-Health-API-Key': self.key},
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if not 200 <= response.status < 300:
                        return False
            except urllib.error.HTTPError as error:
                error.close()
                if error.code in (400, 409, 413, 415, 422):
                    with db:
                        db.execute('UPDATE outbox SET rejected=? WHERE seq=?', (error.code, row[0]))
                return False
            except OSError:
                return False
            with db:
                db.execute('DELETE FROM outbox WHERE seq=?', (row[0],))
            return True
