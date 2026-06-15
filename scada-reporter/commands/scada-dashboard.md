# scada-dashboard

Sistem genel durumu, canlı değerler ve trend verisi.

## Kullanım

```bash
scada dashboard overview [--json]
scada dashboard current-values [--alarm-only] [--watch N] [--json]
scada dashboard trend <tag_id> [tag_id ...] [--hours N] [--json]
```

## `scada dashboard current-values`

Show the latest reading for all tags. The `alarm` column shows alarm state:
- `OVERFLOW` — value > 1,000,000 or quality bad (PLC connection issue)
- `MAX AŞIMI` — value exceeded tag's max_alarm threshold
- `MIN ALTI` — value fell below tag's min_alarm threshold
- `—` — normal, no alarm

```bash
# Show all tags (with alarm column)
scada dashboard current-values

# Show only tags in alarm state
scada dashboard current-values --alarm-only

# Live refresh every 5 seconds, Ctrl+C to stop
scada dashboard current-values --watch 5

# Alarm monitoring loop
scada dashboard current-values --alarm-only --watch 10

# Agent usage: get overflow tags as JSON
scada dashboard current-values --json | jq '[.[] | select(.alarm_state == "overflow")]'
```

## Agent Kullanımı

Canlı veriyi analiz etmek için:

```bash
# Sistem durumu
scada dashboard overview --json

# Tüm tag'lerin anlık değerleri
vals=$(scada dashboard current-values --json)
echo "$vals" | jq '.[] | select(.quality_ok == false) | {name, value}'

# Trend analizi — son 48 saat
scada dashboard trend 1 2 3 --hours 48 --json | jq '.[] | {name, count: (.data | length)}'
```
