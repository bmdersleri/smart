# scada-reports

Zaman bazlı rapor oluşturma. JSON veya Excel çıktı.

## Kullanım

```bash
scada reports generate \
  --tag-ids 1,2,3 \
  --start 2024-01-01T00:00:00 \
  --end 2024-01-02T00:00:00 \
  --interval hourly \
  --format json \
  [--json]
```

## Agent Kullanımı

Veriyi analiz edip raporlamak için:

```bash
# JSON rapor
report=$(scada reports generate --tag-ids 1,2 --start 2024-01-01T00:00:00 --end 2024-01-02T00:00:00 --format json --json)
echo "$report" | jq '.data'
```
