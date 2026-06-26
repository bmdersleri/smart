# Grafana Windows Servis Entegrasyonu

Smart Report, Grafana panellerini uygulama içindeki `/grafana` sayfasında iframe olarak gösterir. Bu kurulumda Grafana Docker container değil, Windows servisidir.

## Varsayılanlar

| Bileşen | Adres |
|---|---|
| Smart Report frontend | `http://localhost:5173` |
| Grafana Windows service | `http://localhost:3000` |
| TimescaleDB | `localhost:5432` |
| Prometheus | `http://localhost:9090` |

Frontend farklı bir Grafana adresi kullanacaksa `.env` içine şunu yazın:

```env
VITE_GRAFANA_URL=http://localhost:3000
```

## Dashboard listesi proxy auth (401 fix)

`/grafana` sayfasındaki dashboard listesi same-origin `/grafana-api` vite proxy'sinden gelir. Proxy, Grafana'ya basic-auth ile bağlanır; böylece Grafana anonymous Viewer kapalı olsa bile `/api/search` **HTTP 401** vermez. Kullanıcı/parola server tarafında kalır, tarayıcıya sızmaz.

Varsayılan `admin:admin`. Farklıysa `scada-reporter/frontend/.env` içine yazın:

```env
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
```

> `/grafana` hâlâ 401 veriyorsa eski service worker önbelleğidir: DevTools → Application → Service Workers → Unregister, ardından Ctrl+Shift+R.

## Provisioning

Yönetici PowerShell açın ve repo kökünden çalıştırın:

```powershell
.\scripts\configure-grafana-windows-service.ps1 -Restart
```

Script şunları yapar:

- `custom.ini` içinde iframe için `allow_embedding = true` ayarlar.
- Anonymous Viewer erişimini açar. Bu, Smart Report içindeki iframe panellerinin login ekranına takılmaması içindir.
- TimescaleDB datasource UID değerini `timescaledb` olarak yazar.
- Prometheus datasource UID değerini `prometheus` olarak yazar.
- Version-controlled dashboard JSON dosyalarını Windows servis provisioning klasörüne kopyalar.

Grafana farklı klasöre kuruluysa:

```powershell
.\scripts\configure-grafana-windows-service.ps1 `
  -GrafanaHome "D:\Tools\GrafanaLabs\grafana" `
  -ServiceName "grafana" `
  -Restart
```

TimescaleDB parolası default değilse:

```powershell
.\scripts\configure-grafana-windows-service.ps1 -PostgresPassword "<parola>" -Restart
```

## Docker Compose

`scada-reporter/docker/docker-compose.yml` içinde Grafana container varsayılan olarak başlamaz; `docker-grafana` profile altındadır. Windows servis Grafana kullanırken normal komut yeterlidir:

```bash
just docker-up
```

Grafana container sadece eski Docker tabanlı yerel akış için istenirse:

```bash
cd scada-reporter/docker
docker compose --profile docker-grafana up -d
```

## Kontrol

Grafana servisinin dashboardları gördüğünü doğrulayın:

```powershell
curl.exe -u admin:admin http://localhost:3000/api/search
```

Smart Report içinde `http://localhost:5173/grafana` sayfasını açın.
