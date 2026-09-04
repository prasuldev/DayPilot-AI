import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from productivity_agent.models import Priority, TaskStatus
from productivity_agent.scheduler import build_plan, build_plan_windows
from productivity_agent.storage import Repository


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.temporary_directory.name) / "agent.db")
        self.repository.initialize()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_orders_by_priority_then_deadline_and_skips_non_fitting_task(self):
        low = self.repository.add_task("Low", Priority.LOW, 30)
        later = self.repository.add_task("Later", Priority.HIGH, 90, datetime(2030, 1, 3))
        sooner = self.repository.add_task("Sooner", Priority.HIGH, 30, datetime(2030, 1, 2))
        start = datetime(2030, 1, 1, 9)

        slots = build_plan([low, later, sooner], start, datetime(2030, 1, 1, 10))

        self.assertEqual([slot.task.id for slot in slots], [sooner.id, low.id])
        self.assertEqual(slots[-1].end_at, datetime(2030, 1, 1, 10))

    def test_persists_and_replaces_schedule(self):
        task = self.repository.add_task("Focus", Priority.HIGH, 60)
        plan_date = date(2030, 1, 1)
        start = datetime(2030, 1, 1, 9)
        slots = build_plan([task], start, datetime(2030, 1, 1, 17))

        first = self.repository.replace_schedule(plan_date, start, datetime(2030, 1, 1, 17), slots)
        second = self.repository.replace_schedule(plan_date, start, datetime(2030, 1, 1, 17), slots)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(second.items), 1)
        self.assertIs(self.repository.get_task(task.id).status, TaskStatus.SCHEDULED)

    def test_multiple_windows_and_breaks(self):
        first = self.repository.add_task("First", Priority.HIGH, 60)
        second = self.repository.add_task("Second", Priority.MEDIUM, 60)
        day = date(2030, 1, 1)
        slots = build_plan_windows(
            [first, second],
            [(datetime.combine(day, datetime.strptime("09:00", "%H:%M").time()),
              datetime.combine(day, datetime.strptime("10:30", "%H:%M").time())),
             (datetime.combine(day, datetime.strptime("13:00", "%H:%M").time()),
              datetime.combine(day, datetime.strptime("15:00", "%H:%M").time()))],
            break_minutes=15,
        )
        self.assertEqual(slots[0].start_at.hour, 9)
        self.assertEqual(slots[1].start_at.hour, 13)

    def test_rejects_overlapping_windows(self):
        day = date(2030, 1, 1)
        with self.assertRaisesRegex(ValueError, "overlap"):
            build_plan_windows([], [(datetime.combine(day, datetime.min.time()), datetime.combine(day, datetime.max.time())),
                                    (datetime.combine(day, datetime.min.time()), datetime.combine(day, datetime.max.time()))])


if __name__ == "__main__":
    unittest.main()
