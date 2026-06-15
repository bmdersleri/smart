# Agent Workflow — SCADA Reporter

Bu kılavuz coding agent'ların SCADA Reporter ile nasıl çalışacağını tanımlar.

## Keşif Akışı

1. `scada health` — API bağlantısını kontrol et
2. `scada auth login` — Kimlik doğrulama
3. `scada tags list --json` — Mevcut tag'leri keşfet
4. `scada dashboard overview --json` — Sistem durumunu öğren

## Operasyonel Akışlar

### Anlık Durum Sorgulama

```bash
scada dashboard current-values --json | jq '.[] | {device, name, value, unit}'
```

### Trend Analizi

```bash
scada dashboard trend 1 2 --hours 24 --json | jq '.[] | {name, avg: (.data | map(.v) | add / length)}'
```

### Rapor Üretimi

```bash
scada reports generate --tag-ids 1,2,3 --start "<dun>" --end "<bugun>" --format json
```

## Hata Yönetimi

- `--json` flag'i her zaman makine-okunabilir çıktı verir
- Hatalar `{"error": true, "detail": "..."}` formatında döner
- `SCADA_TOKEN` env var ile oturum taşınabilir

## İlk Kullanım Senaryosu

1. `scada auth login operator` — Giriş
2. `scada health` — Bağlantı kontrolü
3. `scada tags list --json` — Tag'leri gör
4. `scada dashboard current-values` — Canlı değerleri tablo olarak gör
5. `scada tags readings 1 --limit 5` — Son 5 okumayı kontrol et
