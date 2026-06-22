# scada-tags

PLC tag'lerini listele, oluştur, güncelle, sil ve okumalarını getir.

## Kullanım

```bash
scada tags list [--json-output]
scada tags create --node-id DB171,REAL0 --name "Pompa1_Debi" --unit m3/h --device Pompa1
scada tags update <id> [--unit] [--device] [--channel] [--description] [--min-alarm N] [--max-alarm N] [--json-output]
scada tags delete <id>
scada tags readings <id> [--start ISO] [--end ISO] [--limit N] [--json-output]
```

## `scada tags update`

Update a tag's unit, device, channel, description, or alarm thresholds.

```bash
# Change unit
scada tags update 7 --unit "bar"

# Set alarm thresholds (min must be less than max)
scada tags update 7 --min-alarm 0.5 --max-alarm 6.0

# Multiple fields at once
scada tags update 7 --unit "m3/h" --device "Hat2" --max-alarm 3000

# JSON output (full updated tag object)
scada tags update 7 --min-alarm 0 --max-alarm 5000 --json-output
```

Validation: if `--min-alarm >= --max-alarm`, the request is rejected client-side with an error message.

## Agent Kullanımı

Tag'leri keşfetmek ve okumaları analiz etmek için:

```bash
# Tüm tag'leri JSON olarak al
tags=$(scada tags list --json-output)
echo "$tags" | jq '.[] | {id, name, device, unit}'

# Belirli bir tag'in son okumaları
scada tags readings 1 --limit 10 --json-output | jq '.[] | {t: .timestamp, v: .value}'
```
