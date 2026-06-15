# scada-tags

PLC tag'lerini listele, oluştur, sil ve okumalarını getir.

## Kullanım

```bash
scada tags list [--json]
scada tags create --node-id DB171,REAL0 --name "Pompa1_Debi" --unit m3/h --device Pompa1
scada tags delete <id>
scada tags readings <id> [--start ISO] [--end ISO] [--limit N] [--json]
```

## Agent Kullanımı

Tag'leri keşfetmek ve okumaları analiz etmek için:

```bash
# Tüm tag'leri JSON olarak al
tags=$(scada tags list --json)
echo "$tags" | jq '.[] | {id, name, device, unit}'

# Belirli bir tag'in son okumaları
scada tags readings 1 --limit 10 --json | jq '.[] | {t: .timestamp, v: .value}'
```
