# scada-login

EKONT SMART REPORT API'sine kimlik doğrulama. JWT token alır ve `~/.config/scada-reporter/config.json` dosyasına kaydeder.

## Kullanım

```
scada auth login <kullanici_adi>
```

Sifre prompt ile girilir. `--json-output` flag'i token'ı makine-okunabilir formatta döndürür.

## Agent Kullanımı

```bash
# Giriş yap
scada auth login operator --json-output

# Mevcut kullanıcı bilgisi
scada auth me --json-output
```

## Ortam Değişkeni

```bash
export SCADA_TOKEN="<jwt-token>"
```

Token environment variable olarak da verilebilir — her `scada` çağrısında yeniden giriş gerekmez.
