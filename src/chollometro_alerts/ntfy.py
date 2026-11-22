"""ntfy delivery: publish matches and operational alerts to an ntfy topic.

`NtfyNotifier` implements the same two methods the scanner uses on
`TelegramNotifier` (`send` and `send_system_alert`), so it is a drop-in
replacement selected with `NOTIFIER=ntfy`.  It publishes with ntfy's JSON API
(a POST to the server root with the topic in the body), which keeps non-ASCII
titles and the click-through URL out of HTTP headers.
"""

import time
from datetime import UTC, datetime

from .evaluation import MatchEvidence
from .models import Deal, format_amount
from .telegram import _published_label, post_with_retry

# ntfy's default message limit is 4096 bytes; beyond it the server turns the
# text into an attachment, which is useless on a lock screen.
MAX_MESSAGE_CHARS = 3500
MAX_TITLE_CHARS = 120


# The engine's check labels are fixed Spanish strings, so the match explanation
# is rebuilt from the stable check `code`. Only details that are plain numbers or
# names are quoted; the others (product/brand detection) show the label alone.
CHECK_LABELS = {
    "MAX_PRICE": "Max price",
    "MAX_PRICE_PER_UNIT": "Max price per unit",
    "MAX_PRICE_PER_LITER": "Max price per litre",
    "MAX_PRICE_PER_KILOGRAM": "Max price per kg",
    "MIN_QUANTITY": "Min quantity",
    "MIN_VOLUME": "Min volume",
    "MIN_TEMPERATURE": "Min temperature",
    "MAX_TEMPERATURE": "Max temperature",
    "MAX_AGE": "Max age",
    "MERCHANT_INCLUDED": "Allowed store",
    "MERCHANT_EXCLUDED": "Excluded stores avoided",
    "CATEGORY_INCLUDED": "Category",
    "CATEGORY_EXCLUDED": "Excluded categories avoided",
    "KEYWORD_INCLUDED": "Keyword",
    "KEYWORD_EXCLUDED": "Excluded keywords avoided",
    "PRODUCT": "Product matches",
    "BRAND": "Brand matches",
    "RELEVANCE": "Title matches the search",
}
LABEL_ONLY = frozenset({"PRODUCT", "BRAND", "RELEVANCE"})


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_body(deal: Deal, evidence: MatchEvidence | None, language="en") -> str:
    """English message body: the deal, the alert that matched and why."""
    lines = [
        deal.title,
        "",
        f"Price: {format_amount(deal.price, deal.currency)}",
        f"Store: {deal.merchant or 'N/A'}",
        "Temperature: "
        + (f"{deal.temperature}°" if deal.temperature is not None else "N/A"),
    ]
    posted = _published_label(deal.published_at, language)
    if posted:
        lines.append(posted)
    if evidence is not None:
        alert = (evidence.alert_text or evidence.query or "").strip()
        if alert:
            lines += ["", f'Alert: "{alert}"']
        reasons = []
        for check in evidence.checks:
            label = CHECK_LABELS.get(check.code)
            if label is None:
                continue
            reasons.append(
                f"• {label}"
                if check.code in LABEL_ONLY
                else f"• {label}: {check.detail}"
            )
        if reasons:
            lines += ["Why it matched:", *reasons]
    if deal.url:
        lines += ["", deal.url]
    return "\n".join(lines)


class NtfyNotifier:
    def __init__(self, settings, retries=2, backoff=0.5, sleep=time.sleep):
        self.url = settings.url
        self.topic = settings.topic
        self.priority = settings.priority
        self.language = settings.language
        self.timeout = settings.timeout
        self._headers = (
            {"Authorization": f"Bearer {settings.token}"} if settings.token else None
        )
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep

    def _publish(self, payload):
        post_with_retry(
            self.url,
            json={"topic": self.topic, **payload},
            timeout=self.timeout,
            retries=self.retries,
            backoff=self.backoff,
            sleep=self._sleep,
            headers=self._headers,
        )

    @staticmethod
    def _title(deal: Deal) -> str:
        parts = [format_amount(deal.price, deal.currency)]
        if deal.merchant:
            parts.append(deal.merchant)
        if deal.temperature is not None:
            parts.append(f"{deal.temperature}°")
        return _clip(" · ".join(parts), MAX_TITLE_CHARS)

    def send(self, deal: Deal, evidence: MatchEvidence | None = None, rule_id=None):
        message = build_body(deal, evidence, self.language)
        payload = {
            "title": self._title(deal),
            "message": _clip(message, MAX_MESSAGE_CHARS),
            "priority": self.priority,
            "tags": ["moneybag"],
        }
        if deal.url:
            payload["click"] = deal.url
            payload["actions"] = [
                {"action": "view", "label": "Open deal", "url": deal.url}
            ]
        self._publish(payload)

    def send_system_alert(self, error_type, component, message, run_id):
        text = (
            f"Type: {error_type}\nComponent: {component}\nMessage: {message}\n"
            f"Time: {datetime.now(UTC).isoformat()}\nRun: {run_id}"
        )
        self._publish(
            {
                "title": "chollo-alerts error",
                "message": _clip(text, MAX_MESSAGE_CHARS),
                "priority": 4,
                "tags": ["rotating_light"],
            }
        )
