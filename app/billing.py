"""Stripe の月額プラン（Checkout と Webhook）。"""
import logging

import stripe

from .config import settings
from .store import Store

log = logging.getLogger(__name__)


def checkout_url(user_id: str) -> str | None:
    if not settings.billing_enabled:
        return None
    session = stripe.checkout.Session.create(
        api_key=settings.stripe_secret_key,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        client_reference_id=user_id,
        subscription_data={"metadata": {"user_id": user_id}},
        success_url=f"{settings.public_url}/?paid=1",
        cancel_url=f"{settings.public_url}/",
    )
    return session.url


def handle_webhook(payload: bytes, signature: str, store: Store) -> None:
    """署名を確かめてから会員状態を更新する。署名が不正なら例外。"""
    event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    obj = event["data"]["object"]
    kind = event["type"]
    if kind == "checkout.session.completed" and obj.get("client_reference_id") and obj.get("subscription"):
        store.set_premium(obj["client_reference_id"], obj["subscription"], True)
        log.info("プレミアム開始 user=%s", obj["client_reference_id"])
    elif kind == "customer.subscription.updated":
        user_id = (obj.get("metadata") or {}).get("user_id")
        if user_id:
            store.set_premium(user_id, obj["id"], obj.get("status") in ("active", "trialing"))
    elif kind == "customer.subscription.deleted":
        store.deactivate_subscription(obj["id"])
        log.info("プレミアム終了 subscription=%s", obj["id"])
