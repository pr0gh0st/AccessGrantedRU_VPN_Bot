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
    create_user_if_not_exists,
    get_user_by_telegram_id,
    activate_trial,
    save_vless_profile,
    remove_vless_profile,
    extend_subscription,
    update_traffic_stats,
)
from .functions import InboundClientTraffic, XUIAPI

logger = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    pass


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _is_subscription_active(user: User) -> bool:
    if user.subscription_end is None:
        return False
    return user.subscription_end > _utc_now()


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


async def activate_trial_and_create_vless_profile(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> str:
    """
    Activate trial in DB and create the first VLESS client in XUI.

    Returns VLESS URL.
    """

    if user.is_trial_used:
        raise ServiceError("Trial уже использован.")

    # Prepare stable identifiers used in VLESS URL and DB.
    vless_uuid = str(uuid.uuid4())
    vless_email = f"user-{user.telegram_id}"
    vless_remark = f"AccessGranted-user-{user.telegram_id}"

    # Get inbound details (port), needed for VLESS URL.
    inbound = await xui.get_inbound(settings.INBOUND_ID)
    port = inbound.get("port")
    if not isinstance(port, int):
        raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
    reality_params = xui.extract_reality_params_from_inbound(inbound)

    # 1) Mark trial as used in DB (prevents double-spend).
    try:
        user = await activate_trial(session, telegram_id=user.telegram_id, trial_days=settings.TRIAL_DAYS)
    except Exception as e:
        raise ServiceError(f"Не удалось активировать trial: {e}") from e

    expiry_ms = _to_xui_expiry_ms(user.subscription_end)
    client_settings = {
        # For VLESS/VMESS: `client.id` is UUID.
        "id": vless_uuid,
        # For XUI API compatibility: `email` is often present in responses/payloads.
        "email": vless_email,
        "enable": True,
        "expiryTime": expiry_ms,
        "totalGB": 0,
        "limitIp": 0,
        "tgId": "",
        "subId": "",
        "flow": "",
    }

    # 2) Create the client in XUI. If this fails - rollback DB trial state.
    try:
        await xui.add_client(inbound_id=settings.INBOUND_ID, client=client_settings)
    except Exception as e:
        # Best-effort cleanup in XUI.
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

    vless_url = xui.build_vless_url(
        client_id=vless_uuid,
        host=settings.XUI_HOST,
        port=port,
        remark=vless_remark,
        sni=reality_params.get("sni"),
        sid=reality_params.get("sid"),
        spider_x=reality_params.get("spider_x"),
    )

    vless_profile_data = json.dumps(client_settings, ensure_ascii=False)
    try:
        await save_vless_profile(
            session,
            telegram_id=user.telegram_id,
            vless_uuid=vless_uuid,
            vless_email=vless_email,
            vless_remark=vless_remark,
            vless_profile_data=vless_profile_data,
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
    if not _is_subscription_active(user):
        raise ServiceError("Подписка не активна — создать профиль нельзя.")

    inbound = await xui.get_inbound(settings.INBOUND_ID)
    port = inbound.get("port")
    if not isinstance(port, int):
        raise ServiceError("Не удалось определить port во входящем (inbound) в XUI.")
    reality_params = xui.extract_reality_params_from_inbound(inbound)

    # If already exists in DB - rebuild URL.
    if user.vless_uuid and user.vless_remark:
        return xui.build_vless_url(
            client_id=user.vless_uuid,
            host=settings.XUI_HOST,
            port=port,
            remark=user.vless_remark,
            sni=reality_params.get("sni"),
            sid=reality_params.get("sid"),
            spider_x=reality_params.get("spider_x"),
        )

    vless_uuid = str(uuid.uuid4())
    vless_email = user.vless_email or f"user-{user.telegram_id}"
    vless_remark = user.vless_remark or f"AccessGranted-user-{user.telegram_id}"
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
    await save_vless_profile(
        session,
        telegram_id=user.telegram_id,
        vless_uuid=vless_uuid,
        vless_email=vless_email,
        vless_remark=vless_remark,
        vless_profile_data=vless_profile_data,
    )

    return xui.build_vless_url(
        client_id=vless_uuid,
        host=settings.XUI_HOST,
        port=port,
        remark=vless_remark,
        sni=reality_params.get("sni"),
        sid=reality_params.get("sid"),
        spider_x=reality_params.get("spider_x"),
    )


async def delete_vless_profile_for_user(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> None:
    if not user.vless_uuid:
        raise ServiceError("У вас нет сохранённого VLESS профиля.")

    await xui.remove_client(inbound_id=settings.INBOUND_ID, client_id=user.vless_uuid)
    await remove_vless_profile(session, telegram_id=user.telegram_id)


async def fetch_and_update_traffic_for_user(
    *,
    session: AsyncSession,
    user: User,
    xui: XUIAPI,
) -> InboundClientTraffic:
    if not user.vless_uuid or not user.vless_email:
        raise ServiceError("VLESS профиль не найден — создайте его в разделе «Мой VPN».")

    traffic = await xui.get_client_traffic(
        inbound_id=settings.INBOUND_ID,
        client_id=user.vless_uuid,
        email=user.vless_email,
    )
    if traffic is None:
        raise ServiceError("Не удалось получить трафик из XUI.")

    await update_traffic_stats(
        session,
        telegram_id=user.telegram_id,
        uploaded_bytes=traffic.uploaded_bytes,
        downloaded_bytes=traffic.downloaded_bytes,
    )

    return traffic

