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

## `scada reports list-history`

List the last 10 saved reports.

```bash
scada reports list-history
# id  tarih             tag sayısı  aralık  format
#  3  2026-06-15 22:07           6  hourly  excel
#  2  2026-06-14 18:30           5  hourly  json

scada reports list-history --json
```

## `scada reports download-history`

Re-download a previously generated report (serves cached file, does not regenerate).

```bash
scada reports download-history 3
# ✓ Rapor indirildi: report.xlsx (45,312 byte)

scada reports download-history 3 --output /tmp/myreport.xlsx
```
