# scada-dashboard

Sistem genel durumu, canlı değerler ve trend verisi.

## Kullanım

```bash
scada dashboard overview [--json]
scada dashboard current-values [--json]
scada dashboard trend <tag_id> [tag_id ...] [--hours N] [--json]
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
