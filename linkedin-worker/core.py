"""Conservative queue planning and durable mutation journal (no network I/O)."""
import hashlib
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo('America/Sao_Paulo')
SLOTS = ('08:30', '12:30', '18:00')


def body_hash(body):
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def _date(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamps must include a timezone')
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def plan_posts(catalog, remote, records, now, limit=10):
    """Return original catalog dictionaries extended with a UTC ``due_at``.

    All journal states prevent replay. Unresolved writes also reserve capacity.
    ``remote`` must be the complete channel history and current queue snapshot.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone aware')
    remote_ids = {str(p['id']) for p in remote}
    unresolved = [r for r in records if r['status'] in ('pending', 'inflight', 'uncertain', 'conflict', 'scheduled')
                  and str(r.get('remote_id')) not in remote_ids]
    capacity = min(10, max(0, limit)) - sum(p['status'] == 'scheduled' for p in remote) - len(unresolved)
    if capacity <= 0:
        return []
    seen_ids = {str(r['id']) for r in records}
    seen_hashes = {body_hash(p.get('text', '')) for p in remote}
    seen_hashes.update(r.get('body_hash') for r in records)
    sent_hashes = {body_hash(p.get('text', '')) for p in remote if p['status'] == 'sent'}
    # Confirmed durable history outlives Buffer's remote retention window.
    sent_ids = {str(r['id']) for r in records if r['status'] == 'sent' or any(str(p['id']) == str(r.get('remote_id')) and p['status'] == 'sent' for p in remote)}
    initial_done = all(body_hash(p['body']) in sent_hashes or str(p['id']) in sent_ids
                       for p in catalog if p.get('batch', 'initial') == 'initial')
    occupied = set()
    daily = Counter()
    for p in remote + [dict(status='scheduled', dueAt=r.get('due_at')) for r in unresolved]:
        if p['status'] not in ('sent', 'scheduled') or not p.get('dueAt'):
            continue
        instant = _date(p['dueAt'])
        local = instant.astimezone(LOCAL_TZ)
        daily[local.date()] += 1
        occupied.add((local.date(), local.strftime('%H:%M')))
    earliest = now.astimezone(timezone.utc) + timedelta(minutes=30)
    result = []
    for p in sorted(catalog, key=lambda p: (p.get('batch', 'initial') != 'initial', p['order'])):
        digest = body_hash(p['body'])
        if str(p['id']) in seen_ids or digest in seen_hashes:
            prior_times = [_date(r['due_at']) for r in records if str(r['id']) == str(p['id']) and r.get('due_at')]
            prior_times.extend(_date(r['dueAt']) for r in remote if body_hash(r.get('text', '')) == digest and r.get('dueAt'))
            if prior_times:
                earliest = max(earliest, max(prior_times) + timedelta(microseconds=1))
            continue
        if p.get('batch', 'initial') != 'initial' and not initial_done:
            continue
        slot = p['slot']
        if slot not in SLOTS:
            raise ValueError(f'Invalid slot: {slot}')
        day = earliest.astimezone(LOCAL_TZ).date()
        while True:
            candidate = datetime.combine(day, time.fromisoformat(slot), LOCAL_TZ)
            if candidate >= earliest and daily[day] < 3 and (day, slot) not in occupied:
                break
            day += timedelta(days=1)
        result.append(dict(p, due_at=_iso(candidate)))
        daily[day] += 1
        occupied.add((day, slot))
        seen_hashes.add(digest)
        seen_ids.add(str(p['id']))
        earliest = candidate.astimezone(timezone.utc) + timedelta(microseconds=1)
        if len(result) >= capacity:
            break
    return result


class Journal:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, status TEXT NOT NULL, body_hash TEXT NOT NULL, due_at TEXT, remote_id TEXT, detail TEXT)')

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def records(self):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM posts ORDER BY rowid')]

    def mark(self, id, status, body, due_at=None, remote_id=None, detail=None):
        with self._connect() as conn:
            conn.execute('INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, body_hash=excluded.body_hash, due_at=COALESCE(excluded.due_at,posts.due_at), remote_id=COALESCE(excluded.remote_id,posts.remote_id), detail=excluded.detail',
                         (str(id), status, body_hash(body), _iso(_date(due_at)) if due_at else None, str(remote_id) if remote_id is not None else None, detail))

    def reconcile(self, remote):
        with self._connect() as conn:
            for row in conn.execute('SELECT * FROM posts').fetchall():
                matches = [p for p in remote if row['remote_id'] is not None and str(p['id']) == row['remote_id']]
                if not matches and row['status'] in ('pending', 'inflight', 'uncertain', 'conflict'):
                    matches = [p for p in remote if body_hash(p.get('text', '')) == row['body_hash'] and row['due_at'] and p.get('dueAt') and _date(p['dueAt']) == _date(row['due_at'])]
                if len(matches) > 1:
                    conn.execute("UPDATE posts SET status='conflict',detail='Multiple remote matches; manual review required' WHERE id=?", (row['id'],))
                elif len(matches) == 1:
                    p = matches[0]
                    if row['status'] == 'uncertain':
                        try:
                            verified = (body_hash(p.get('text', '')) == row['body_hash']
                                        and row['due_at'] and p.get('dueAt')
                                        and _date(p['dueAt']) == _date(row['due_at']))
                        except (ValueError, TypeError, AttributeError):
                            verified = False
                        if not verified:
                            continue
                    conn.execute('UPDATE posts SET status=?,remote_id=?,detail=? WHERE id=?', (p['status'], str(p['id']), 'Reconciled with remote', row['id']))
                elif row['status'] == 'inflight':
                    conn.execute("UPDATE posts SET status='uncertain',detail='No remote match; do not automatically resubmit' WHERE id=?", (row['id'],))


@contextmanager
def run_lock(path):
    """Exclusive cross-process lock; abandoned locks require manual inspection."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()
