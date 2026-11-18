"""The planning week, used everywhere a date's week, deadline or lock is needed.

A work week runs Monday to Friday. Its plan is due at PLAN_DEADLINE_TIME on the Friday
before, in APP_TIMEZONE: the week is *open* before that moment and *locked* from it on.
From 00:00 that Friday until the deadline, users who have not planned see a reminder.
Saturday and Sunday belong to the week that starts on the Monday before them.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.core.config import Settings


def utcnow() -> datetime:
    """The current time. Tests replace this to move the clock."""
    return datetime.now(UTC)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def today(settings: Settings) -> date:
    return utcnow().astimezone(settings.tz).date()


@dataclass(frozen=True)
class PlanWeek:
    start: date
    """Monday."""
    end: date
    """Friday."""
    deadline: datetime
    """The plan is due at this moment (time-zone aware)."""
    reminder_from: datetime
    """Friday 00:00 before the week: the reminder shows from here until the deadline."""
    is_open: bool
    in_reminder_window: bool
    """Now is between `reminder_from` and the deadline."""

    @property
    def days(self) -> list[date]:
        """Monday to Friday."""
        return [self.start + timedelta(days=i) for i in range(5)]


def plan_week(day: date, settings: Settings) -> PlanWeek:
    """The planning week containing `day`, and whether it is still open now."""
    start = monday_of(day)
    friday_before = start - timedelta(days=3)
    deadline = datetime.combine(friday_before, settings.plan_deadline_time, tzinfo=settings.tz)
    reminder_from = datetime.combine(friday_before, time(), tzinfo=settings.tz)
    now = utcnow()
    return PlanWeek(
        start=start,
        end=start + timedelta(days=4),
        deadline=deadline,
        reminder_from=reminder_from,
        is_open=now < deadline,
        in_reminder_window=reminder_from <= now < deadline,
    )


def next_week(settings: Settings) -> PlanWeek:
    """The week starting on the next Monday after today."""
    return plan_week(monday_of(today(settings)) + timedelta(days=7), settings)
