import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core import Journal, body_hash, plan_posts, run_lock


def post(i, slot='08:30', batch='initial'):
    return dict(id=str(i), body=f'Text {i}', slot=slot, batch=batch, order=i)


class PlannerTests(unittest.TestCase):
    now = datetime(2026, 11, 20, 11, 10, tzinfo=timezone.utc)

    def test_future_margin_timezone_and_order(self):
        result = plan_posts([post(1), post(2, '12:30'), post(3, '18:00')], [], [], self.now)
        self.assertEqual([p['due_at'] for p in result], [
            '2026-11-21T11:30:00Z', '2026-11-21T15:30:00Z', '2026-11-21T21:00:00Z'])

    def test_overdue_remote_consumes_capacity(self):
        remote = [dict(id=str(i), text=f'manual {i}', status='scheduled', dueAt='2020-01-01T11:30:00Z') for i in range(10)]
        self.assertEqual(plan_posts([post(1)], remote, [], self.now), [])

    def test_manual_daily_capacity_and_occupied_slot(self):
        remote = [dict(id=str(i), text=f'manual {i}', status='sent', dueAt=f'2026-11-20T{h}:00:00Z') for i,h in enumerate(['10','12','14'])]
        result = plan_posts([post(1, '18:00')], remote, [], self.now)
        self.assertEqual(result[0]['due_at'], '2026-11-21T21:00:00Z')

    def test_dedup_and_initial_gate(self):
        catalog = [post(1), post(2), post(3, batch='daily')]
        remote = [dict(id='r1', text='Text 1', status='sent', dueAt='2026-11-19T11:30:00Z')]
        records = [dict(id='2', status='uncertain', body_hash=body_hash('Text 2'))]
        self.assertEqual(plan_posts(catalog, remote, records, self.now), [])

    def test_daily_allowed_only_after_initial_sent(self):
        remote = [dict(id='r1', text='Text 1', status='sent', dueAt='2026-11-19T11:30:00Z')]
        self.assertEqual(len(plan_posts([post(1), post(2, batch='daily')], remote, [], self.now)), 1)

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            plan_posts([], [], [], datetime(2026, 1, 1))

    def test_daily_allowed_after_initial_sent_history_expires(self):
        records = [dict(id='1', status='sent', body_hash=body_hash('Text 1'), remote_id='expired')]
        planned = plan_posts([post(1), post(2, batch='daily')], [], records, self.now)
        self.assertEqual([p['id'] for p in planned], ['2'])

    def test_initial_order_follows_already_scheduled_item(self):
        remote = [dict(id='r1', text='Text 1', status='scheduled', dueAt='2026-11-23T11:30:00Z')]
        planned = plan_posts([post(1), post(2, '12:30')], remote, [], self.now)
        self.assertEqual(planned[0]['due_at'], '2026-11-23T15:30:00Z')


class JournalTests(unittest.TestCase):
    def test_crash_recovery_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.db'
            journal = Journal(path)
            journal.mark('1', 'inflight', 'Text 1', '2026-11-20T11:30:00Z')
            journal = Journal(path)
            journal.reconcile([dict(id='r1', text='Text 1', dueAt='2026-11-20T08:30:00-03:00', status='scheduled')])
            self.assertEqual(journal.records()[0]['remote_id'], 'r1')
            journal.mark('2', 'uncertain', 'Text 2', '2026-11-21T11:30:00Z')
            journal.reconcile([dict(id=f'r{i}', text='Text 2', dueAt='2026-11-21T11:30:00Z', status='scheduled') for i in range(2)])
            self.assertEqual(journal.records()[1]['status'], 'conflict')

    def test_uncertain_readback_requires_original_body_and_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal(Path(tmp) / 'state.db')
            journal.mark('1', 'uncertain', 'Text 1', '2026-11-20T11:30:00Z', 'r1')
            remote = dict(id='r1', text='Wrong body', dueAt='2026-11-20T11:30:00Z', status='scheduled')
            journal.reconcile([remote])
            self.assertEqual(journal.records()[0]['status'], 'uncertain')
            remote.update(text='Text 1', dueAt='2026-11-21T11:30:00Z')
            journal.reconcile([remote])
            self.assertEqual(journal.records()[0]['status'], 'uncertain')
            remote['dueAt'] = '2026-11-20T08:30:00-03:00'
            journal.reconcile([remote])
            self.assertEqual(journal.records()[0]['status'], 'scheduled')

    def test_lock_excludes_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'run.lock'
            with run_lock(path):
                with self.assertRaises(FileExistsError):
                    with run_lock(path):
                        pass
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
