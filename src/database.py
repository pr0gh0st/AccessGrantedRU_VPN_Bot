from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings


class Base(DeclarativeBase):
    pass


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _add_months_to_datetime(value: dt.datetime, months: int) -> dt.datetime:
    """
    Add months to a datetime without external dependencies.

    If the target month has fewer days, clamp to the last day of that month.
    """

    if months == 0:
        return value
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware (UTC recommended).")

    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1

    # Clamp day to end of month
    last_day = dt.date(year, month, 1).replace(day=28)  # helper to get end-of-month
    last_day = (last_day + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    day = min(value.day, last_day.day)

    return value.replace(year=year, month=month, day=day)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    subscription_start: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_end: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Значение subscription_end, для которого уже отправлено напоминание (чтобы не дублировать при продлении).
    reminder_24h_for_subscription_end: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_1h_for_subscription_end: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    vless_uuid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vless_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vless_remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vless_profile_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_uploaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_downloaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_traffic_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StaticProfile(Base):
    __tablename__ = "static_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    vless_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(16))

    plan_code: Mapped[str] = mapped_column(String(64), index=True)
    months: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)

    provider_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminBroadcastLog(Base):
    __tablename__ = "admin_broadcast_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text)
    total_users: Mapped[int] = mapped_column(Integer)
    success_count: Mapped[int] = mapped_column(Integer)
    fail_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _sqlite_add_user_reminder_columns(conn) -> None:
    if "sqlite" not in settings.DATABASE_URL.lower():
        return
    result = await conn.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in result.all()}
    if not cols:
        return
    if "reminder_24h_for_subscription_end" not in cols:
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN reminder_24h_for_subscription_end DATETIME")
        )
    if "reminder_1h_for_subscription_end" not in cols:
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN reminder_1h_for_subscription_end DATETIME")
        )


async def init_db() -> None:
    """Create DB tables if they do not exist."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _sqlite_add_user_reminder_columns(conn)


async def create_user_if_not_exists(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    is_admin: bool = False,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is not None:
        # Keep original subscription fields; update profile fields for better admin UX.
        user.username = username
        user.full_name = full_name
        user.is_admin = bool(user.is_admin or is_admin)
        await session.commit()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        is_admin=bool(is_admin),
        is_trial_used=False,
        is_active=False,
    )
    session.add(user)
    await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def extend_subscription(session: AsyncSession, *, telegram_id: int, months: int) -> User:
    if months <= 0:
        raise ValueError("months must be > 0")

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    now = _utc_now()
    base_end = user.subscription_end or now
    if base_end <= now:
        base_end = now

    new_end = _add_months_to_datetime(base_end, months)
    if user.subscription_start is None or user.subscription_start <= now - dt.timedelta(days=365 * 100):
        user.subscription_start = now

    user.subscription_end = new_end
    user.is_active = True
    await session.commit()
    return user


async def activate_trial(session: AsyncSession, *, telegram_id: int, trial_days: int) -> User:
    if trial_days <= 0:
        raise ValueError("trial_days must be > 0")

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    if user.is_trial_used:
        raise ValueError("Trial already used")

    now = _utc_now()
    user.is_trial_used = True
    user.subscription_start = now
    user.subscription_end = now + dt.timedelta(days=trial_days)
    user.is_active = True
    await session.commit()
    return user


async def deactivate_expired_users(session: AsyncSession) -> int:
    """Deactivate users whose subscription_end is in the past."""

    now = _utc_now()
    stmt = (
        update(User)
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end <= now)
        .where(User.is_active.is_(True))
        .values(is_active=False)
    )
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount or 0)


async def save_vless_profile(
    session: AsyncSession,
    *,
    telegram_id: int,
    vless_uuid: str,
    vless_email: str,
    vless_remark: str,
    vless_profile_data: str,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    user.vless_uuid = vless_uuid
    user.vless_email = vless_email
    user.vless_remark = vless_remark
    user.vless_profile_data = vless_profile_data
    user.is_active = True
    await session.commit()
    return user


async def remove_vless_profile(session: AsyncSession, *, telegram_id: int) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    user.vless_uuid = None
    user.vless_email = None
    user.vless_remark = None
    user.vless_profile_data = None
    # Keep subscription fields intact; only remove the client/profile mapping.
    await session.commit()
    return user


async def get_all_users(session: AsyncSession, *, offset: int = 0, limit: int = 50) -> list[User]:
    stmt = select(User).order_by(User.id.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_users(session: AsyncSession, *, offset: int = 0, limit: int = 50) -> list[User]:
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.id.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_users_subscription_ending_within(
    session: AsyncSession,
    *,
    now: dt.datetime,
    within_hours: int = 48,
    limit: int = 5000,
) -> list[User]:
    """Активные пользователи с окончанием подписки в ближайшие `within_hours` (для напоминаний)."""

    horizon = now + dt.timedelta(hours=within_hours)
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end > now)
        .where(User.subscription_end <= horizon)
        .order_by(User.subscription_end.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_expiring_users(
    session: AsyncSession,
    *,
    within_hours: int = 24,
    offset: int = 0,
    limit: int = 50,
) -> list[User]:
    now = _utc_now()
    end = now + dt.timedelta(hours=within_hours)
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end >= now)
        .where(User.subscription_end <= end)
        .order_by(User.subscription_end.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_expired_active_users(session: AsyncSession, *, limit: int = 200) -> list[User]:
    now = _utc_now()
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end <= now)
        .order_by(User.subscription_end.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_admins(session: AsyncSession) -> list[User]:
    stmt = select(User).where(User.is_admin.is_(True)).order_by(User.id.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_static_profile(session: AsyncSession, *, name: str, vless_url: str) -> StaticProfile:
    profile = StaticProfile(name=name, vless_url=vless_url)
    session.add(profile)
    await session.commit()
    return profile


async def delete_static_profile(session: AsyncSession, *, profile_id: int) -> None:
    from sqlalchemy import delete

    del_stmt = delete(StaticProfile).where(StaticProfile.id == profile_id)
    await session.execute(del_stmt)
    await session.commit()


async def list_static_profiles(session: AsyncSession) -> list[StaticProfile]:
    stmt = select(StaticProfile).order_by(StaticProfile.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def save_payment_log(
    session: AsyncSession,
    *,
    telegram_id: int,
    amount: int,
    currency: str,
    plan_code: str,
    months: int,
    payload: str,
    provider_payment_charge_id: Optional[str],
    telegram_payment_charge_id: Optional[str],
    status: str,
) -> PaymentLog:
    log = PaymentLog(
        telegram_id=telegram_id,
        amount=amount,
        currency=currency,
        plan_code=plan_code,
        months=months,
        payload=payload,
        provider_payment_charge_id=provider_payment_charge_id,
        telegram_payment_charge_id=telegram_payment_charge_id,
        status=status,
    )
    session.add(log)
    await session.commit()
    return log


async def update_traffic_stats(
    session: AsyncSession,
    *,
    telegram_id: int,
    uploaded_bytes: int,
    downloaded_bytes: int,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    uploaded_bytes = max(0, int(uploaded_bytes))
    downloaded_bytes = max(0, int(downloaded_bytes))
    traffic = uploaded_bytes + downloaded_bytes

    user.total_uploaded_bytes += uploaded_bytes
    user.total_downloaded_bytes += downloaded_bytes
    user.total_traffic_bytes += traffic
    await session.commit()
    return user


async def count_users_total(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(User))
    return int(r.scalar_one() or 0)


async def count_users_with_active_subscription(session: AsyncSession) -> int:
    now = _utc_now()
    r = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end > now)
    )
    return int(r.scalar_one() or 0)


async def count_users_trial_used(session: AsyncSession) -> int:
    r = await session.execute(select(func.count()).select_from(User).where(User.is_trial_used.is_(True)))
    return int(r.scalar_one() or 0)


async def count_users_expired_subscription(session: AsyncSession) -> int:
    now = _utc_now()
    r = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.subscription_end.is_not(None))
        .where(User.subscription_end <= now)
    )
    return int(r.scalar_one() or 0)


async def sum_payment_amounts(
    session: AsyncSession,
    *,
    status: Optional[str] = None,
) -> int:
    stmt = select(func.coalesce(func.sum(PaymentLog.amount), 0))
    if status is not None:
        stmt = stmt.where(PaymentLog.status == status)
    r = await session.execute(stmt)
    return int(r.scalar_one() or 0)


async def sum_payment_amounts_successful(session: AsyncSession) -> int:
    """Sum amounts for typical successful payment statuses (Telegram Payments)."""

    ok_statuses = ("success", "completed", "paid", "ok")
    stmt = select(func.coalesce(func.sum(PaymentLog.amount), 0)).where(PaymentLog.status.in_(ok_statuses))
    r = await session.execute(stmt)
    return int(r.scalar_one() or 0)


async def get_recent_payment_logs(session: AsyncSession, *, limit: int = 20) -> list[PaymentLog]:
    stmt = select(PaymentLog).order_by(PaymentLog.id.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def save_admin_broadcast_log(
    session: AsyncSession,
    *,
    text: str,
    total_users: int,
    success_count: int,
    fail_count: int,
) -> AdminBroadcastLog:
    row = AdminBroadcastLog(
        text=text,
        total_users=total_users,
        success_count=success_count,
        fail_count=fail_count,
    )
    session.add(row)
    await session.commit()
    return row


async def search_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    return await get_user_by_telegram_id(session, telegram_id)


async def search_users_by_username(session: AsyncSession, *, username_query: str, limit: int = 20) -> list[User]:
    q = username_query.strip().lstrip("@")
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(User)
        .where(User.username.is_not(None))
        .where(User.username.ilike(pattern))
        .order_by(User.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def extend_subscription_by_days(session: AsyncSession, *, telegram_id: int, days: int) -> User:
    if days == 0:
        raise ValueError("days must be non-zero")

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    now = _utc_now()
    delta = dt.timedelta(days=abs(days))
    if days > 0:
        base = user.subscription_end or now
        if base <= now:
            base = now
        new_end = base + delta
        if user.subscription_start is None:
            user.subscription_start = now
        user.subscription_end = new_end
        user.is_active = True
    else:
        if user.subscription_end is None:
            raise ValueError("Нет даты окончания подписки — уменьшать нечего")
        new_end = user.subscription_end - delta
        user.subscription_end = new_end
        if new_end <= now:
            user.is_active = False

    await session.commit()
    return user


async def get_all_telegram_ids(session: AsyncSession) -> list[int]:
    stmt = select(User.telegram_id)
    result = await session.execute(stmt)
    return [int(x) for x in result.scalars().all()]


async def reset_trial_for_user(session: AsyncSession, *, telegram_id: int) -> User:
    """
    Reset trial state for a specific user.

    Intended for admin recovery/debug operations.
    """

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("User not found")

    user.is_trial_used = False
    # Reset trial-linked subscription state and profile mapping.
    user.subscription_start = None
    user.subscription_end = None
    user.reminder_24h_for_subscription_end = None
    user.reminder_1h_for_subscription_end = None
    user.is_active = False
    user.vless_uuid = None
    user.vless_email = None
    user.vless_remark = None
    user.vless_profile_data = None

    await session.commit()
    return user

