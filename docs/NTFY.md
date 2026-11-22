# ntfy delivery (no Telegram)

Set `NOTIFIER=ntfy` to publish matches to an [ntfy](https://ntfy.sh) topic instead of
Telegram. Only the `scan` command is supported in this mode: there is no chat
listener, so alerts are managed from files.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NOTIFIER` | `telegram` | `telegram` or `ntfy` |
| `NTFY_URL` | required | Server base URL, e.g. `https://ntfy.example.com` |
| `NTFY_TOPIC` | required | Topic to publish to (letters, digits, `-`, `_`) |
| `NTFY_TOKEN` | unset | Optional bearer token for protected servers |
| `NTFY_PRIORITY` | `3` | Priority for matches, 1-5 (errors use 4) |
| `NTFY_LANGUAGE` | `en` | Language of the message frame |

Manage alerts with a JSON file (no LLM and no Telegram needed):

```
chollo-alerts alert import alerts.json --dry-run   # validate
chollo-alerts alert import alerts.json             # idempotent, keyed on "name"
chollo-alerts alert list
chollo-alerts alert delete 3
```

Each entry is an `AlertRule` (`query`, `brand`, `include_merchants`, `exclude_merchants`,
`constraints.max_price`, `constraints.temperature_min`, ...) plus a unique `name`. See
`examples/alerts.example.json`.

Imported rules set `require_query_match`: the query must appear in the deal title (any
order; `9070 xt` and `9070xt` are equivalent) in addition to the price, merchant and
temperature limits. Without it, a rule with no product type or brand would match every new
deal under its price cap, because the scanner evaluates each new deal against every rule.

Alerts only fire for deals published after the alert was imported. For a UK install set
`PEPPER_SITE=hotukdeals` and `ALERT_TIMEZONE=Europe/London`, and run the container with
the `scan` command.
