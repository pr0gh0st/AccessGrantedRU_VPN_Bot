from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import (
    User,
    activate_trial,
    add_user_vless_key,
    create_user_if_not_exists,
    delete_owned_user_vless_key,
    get_user_vless_key_owned,
    list_user_vless_keys,
    remove_vless_profile,
    update_traffic_stats,
)
from .functions import InboundClientTraffic, XUIAPI
from .utils import format_datetime_ru

logger = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    pass


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _normalize_db_datetime_utc(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """SQLite often returns naive datetimes; treat them as UTC for comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _is_subscription_active(user: User) -> bool:
    end = _normalize_db_datetime_utc(user.subscription_end)
    if end is None:
        return False
    return end > _utc_now()


def _to_xui_expiry_ms(value: Optional[dt.datetime]) -> int:
    """
    Convert datetime to unix milliseconds for 3X-UI client `expiryTime`.
    0 means unlimited in XUI.
    """

    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return int(value.timestamp() * 1000)


async def push_key_expiry_to_xui(
    xui: XUIAPI,
    *,
    vless_uuid: str,
    vless_email: str,
    subscription_end: Optional[dt.datetime],
) -> None:
    await xui.update_client_expiry_ms(
        inbound_id=settings.INBOUND_ID,
        client_id=vless_uuid,
        expiry_ms=_to_xui_expiry_ms(subscription_end),
        email=vless_email,
    )


async def get_or_create_user(
    *,
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: Optional[str],
) -> User:
    is_admin = telegram_id in settings.admin_ids
    return await create_user_if_not_exists(
        session,
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        is_admin=is_admin,
    )


def _build_vless_url_for_key(
    *,
    xui: XUIAPI,
    vless_uuid: str,
    vless_remark: str,
    port: int,
    reality_params: dict,
) -> str:
    return xui.build_vless_url(
        client_id=vless_uuid,
        host=settings.XUI_HOST,
        port=port,
        remark=vless_remark,
        sni=reality_params.get("sni"),
        sid=reality_params.get("sid"),
        spider_x=reality_params.get("spider_x"),
    )


async def activate_trial_and_create_vless_profile(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> str:
    """
    Activate trial in DB and create the first VLESS client in XUI.

    One trial per Telegram user forever: `is_trial_used` stays True after the first
    activation (even if subscription expires or XUI client is removed). Only an admin
    can reset `is_trial_used` via `reset_trial_for_user`.

    Returns VLESS URL.
    """

    if user.is_trial_used:
        raise ServiceError("Trial уже использован.")

    vless_uuid = str(uuid.uuid4())
    vless_email = f"user-{user.telegram_id}"
    vless_remark = f"AccessGranted-user-{user.telegram_id}-k1"

    inbound = await xui.get_inbound(settings.INBOUND_ID)
    port = inbound.get("port")
    if not isinstance(port, int):
        raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
    reality_params = xui.extract_reality_params_from_inbound(inbound)

    try:
        user = await activate_trial(session, telegram_id=user.telegram_id, trial_days=settings.TRIAL_DAYS)
    except Exception as e:
        raise ServiceError(f"Не удалось активировать trial: {e}") from e

    expiry_ms = _to_xui_expiry_ms(user.subscription_end)
    client_settings = {
        "id": vless_uuid,
        "email": vless_email,
        "enable": True,
        "expiryTime": expiry_ms,
        "totalGB": 0,
        "limitIp": 0,
        "tgId": "",
        "subId": "",
        "flow": "",
    }

    try:
        await xui.add_client(inbound_id=settings.INBOUND_ID, client=client_settings)
    except Exception as e:
        try:
            await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=vless_uuid)
        except Exception:
            logger.warning("Best-effort XUI remove_client failed after trial add failure")

        user.is_trial_used = False
        user.subscription_start = None
        user.subscription_end = None
        user.is_active = False
        user.vless_uuid = None
        user.vless_email = None
        user.vless_remark = None
        user.vless_profile_data = None
        await session.commit()

        raise ServiceError(f"Не удалось создать VLESS профиль в XUI: {e}") from e

    vless_url = _build_vless_url_for_key(
        xui=xui,
        vless_uuid=vless_uuid,
        vless_remark=vless_remark,
        port=port,
        reality_params=reality_params,
    )

    vless_profile_data = json.dumps(client_settings, ensure_ascii=False)
    try:
        await add_user_vless_key(
            session,
            user_id=user.id,
            vless_uuid=vless_uuid,
            vless_email=vless_email,
            vless_remark=vless_remark,
            vless_profile_data=vless_profile_data,
            subscription_end=user.subscription_end,
        )
    except Exception as e:
        raise ServiceError(f"Не удалось сохранить VLESS профиль в БД: {e}") from e

    return vless_url


async def ensure_vless_profile_for_user(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> str:
    """Первый бесплатный ключ при активной подписке, если ключей ещё нет."""

    if not _is_subscription_active(user):
        raise ServiceError("Подписка не активна — создать профиль нельзя.")

    keys = await list_user_vless_keys(session, user_id=user.id)
    if keys:
        inbound = await xui.get_inbound(settings.INBOUND_ID)
        port = inbound.get("port")
        if not isinstance(port, int):
            raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
        reality_params = xui.extract_reality_params_from_inbound(inbound)
        k = keys[0]
        return _build_vless_url_for_key(
            xui=xui,
            vless_uuid=k.vless_uuid,
            vless_remark=k.vless_remark,
            port=port,
            reality_params=reality_params,
        )

    inbound = await xui.get_inbound(settings.INBOUND_ID)
    port = inbound.get("port")
    if not isinstance(port, int):
        raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
    reality_params = xui.extract_reality_params_from_inbound(inbound)

    vless_uuid = str(uuid.uuid4())
    n = 1
    vless_email = f"user-{user.telegram_id}-k{n}"
    vless_remark = f"AccessGranted-user-{user.telegram_id}-k{n}"
    client_settings = {
        "id": vless_uuid,
        "email": vless_email,
        "enable": True,
        "expiryTime": _to_xui_expiry_ms(user.subscription_end),
        "totalGB": 0,
        "limitIp": 0,
        "tgId": "",
        "subId": "",
        "flow": "",
    }

    await xui.add_client(inbound_id=settings.INBOUND_ID, client=client_settings)

    vless_profile_data = json.dumps(client_settings, ensure_ascii=False)
    await add_user_vless_key(
        session,
        user_id=user.id,
        vless_uuid=vless_uuid,
        vless_email=vless_email,
        vless_remark=vless_remark,
        vless_profile_data=vless_profile_data,
        subscription_end=user.subscription_end,
    )

    return _build_vless_url_for_key(
        xui=xui,
        vless_uuid=vless_uuid,
        vless_remark=vless_remark,
        port=port,
        reality_params=reality_params,
    )


async def create_extra_vless_key_trial(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> str:
    """Дополнительный ключ с бесплатным пробным периодом (только срок ключа, не общая подписка)."""

    keys = await list_user_vless_keys(session, user_id=user.id)
    n_existing = len(keys)
    if n_existing < 1:
        raise ServiceError("Сначала создайте первый ключ.")
    if n_existing >= settings.MAX_VLESS_KEYS:
        raise ServiceError(f"Достигнут лимит ключей ({settings.MAX_VLESS_KEYS}).")

    now = _utc_now()
    if not any(k.subscription_end and k.subscription_end > now for k in keys):
        raise ServiceError("Нужен хотя бы один ключ с не истёкшим сроком доступа.")

    trial_end = now + dt.timedelta(minutes=settings.EXTRA_KEY_TRIAL_MINUTES)
    expiry_ms = _to_xui_expiry_ms(trial_end)

    inbound = await xui.get_inbound(settings.INBOUND_ID)
    port = inbound.get("port")
    if not isinstance(port, int):
        raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
    reality_params = xui.extract_reality_params_from_inbound(inbound)

    n = n_existing + 1
    vless_uuid = str(uuid.uuid4())
    vless_email = f"user-{user.telegram_id}-k{n}"
    vless_remark = f"AccessGranted-user-{user.telegram_id}-k{n}"
    client_settings = {
        "id": vless_uuid,
        "email": vless_email,
        "enable": True,
        "expiryTime": expiry_ms,
        "totalGB": 0,
        "limitIp": 0,
        "tgId": "",
        "subId": "",
        "flow": "",
    }

    await xui.add_client(inbound_id=settings.INBOUND_ID, client=client_settings)
    vless_profile_data = json.dumps(client_settings, ensure_ascii=False)
    await add_user_vless_key(
        session,
        user_id=user.id,
        vless_uuid=vless_uuid,
        vless_email=vless_email,
        vless_remark=vless_remark,
        vless_profile_data=vless_profile_data,
        subscription_end=trial_end,
    )

    return _build_vless_url_for_key(
        xui=xui,
        vless_uuid=vless_uuid,
        vless_remark=vless_remark,
        port=port,
        reality_params=reality_params,
    )


async def delete_vless_profile_for_user(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> None:
    keys = await list_user_vless_keys(session, user_id=user.id)
    if not keys:
        raise ServiceError("У вас нет сохранённых VLESS ключей.")

    for k in keys:
        try:
            await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=k.vless_uuid)
        except Exception:
            logger.warning("remove_client failed for uuid=%s", k.vless_uuid, exc_info=True)

    await remove_vless_profile(session, telegram_id=user.telegram_id)


async def delete_single_vless_key_for_user(
    *,
    session: AsyncSession,
    user: User,
    key_id: int,
    xui: XUIAPI,
) -> None:
    key = await get_user_vless_key_owned(session, key_id=key_id, telegram_id=user.telegram_id)
    if key is None:
        raise ServiceError("Ключ не найден.")

    await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=key.vless_uuid)
    await delete_owned_user_vless_key(session, key_id=key_id, telegram_id=user.telegram_id)


async def fetch_and_update_traffic_for_user(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> InboundClientTraffic:
    keys = await list_user_vless_keys(session, user_id=user.id)
    if not keys:
        raise ServiceError("VLESS ключи не найдены — создайте их в разделе «Мой VPN».")

    total_up = 0
    total_down = 0
    for k in keys:
        traffic = await xui.get_client_traffic(
            inbound_id=settings.INBOUND_ID,
            client_id=k.vless_uuid,
            email=k.vless_email,
        )
        if traffic is None:
            raise ServiceError("Не удалось получить трафик из XUI.")
        total_up += traffic.uploaded_bytes
        total_down += traffic.downloaded_bytes

    await update_traffic_stats(
        session,
        telegram_id=user.telegram_id,
        uploaded_bytes=total_up,
        downloaded_bytes=total_down,
    )

    return InboundClientTraffic(
        uploaded_bytes=total_up,
        downloaded_bytes=total_down,
        total_bytes=total_up + total_down,
    )


def format_admin_user_card(user: User, *, vless_keys_count: int = 0) -> str:
    sub_ok = _is_subscription_active(user)
    uname = f"@{user.username}" if user.username else "—"
    return (
        f"ID: `{user.telegram_id}` | {uname}\n"
        f"Имя: {user.full_name or '—'}\n"
        f"Trial использован: {'да' if user.is_trial_used else 'нет'}\n"
        f"Подписка активна: {'да' if sub_ok else 'нет'}\n"
        f"До: {format_datetime_ru(user.subscription_end)}\n"
        f"VLESS ключей: {vless_keys_count}"
    )


def user_can_activate_trial(user: User) -> bool:
    return not user.is_trial_used


async def user_can_add_extra_key_trial(
    session: AsyncSession, *, user: User, keys_count: int
) -> bool:
    if keys_count < 1 or keys_count >= settings.MAX_VLESS_KEYS:
        return False
    keys = await list_user_vless_keys(session, user_id=user.id)
    now = _utc_now()
    return any(k.subscription_end and k.subscription_end > now for k in keys)
