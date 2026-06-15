# Plan: KEPServerEX → S7-1500 Built-in OPC UA

## Context

KEPServerEX OPC UA bağlantısı `BadUserAccessDenied` hatasıyla çözümsüz kaldı. S7-1500'ün TIA Portal üzerinden etkinleştirilen built-in OPC UA sunucusuna doğrudan bağlanmaya geçiliyor. Bu yaklaşım:
- KEPServerEX lisans/auth sorununu ortadan kaldırır
- Sertifika karmaşıklığını kaldırır (None güvenlik modu ile Anonymous bağlantı)
- Doğrudan asyncua bağlantısı, aradaki broker yok

**PLC IP:** `192.168.112.50`
**Port:** `4840` (standart OPC UA)
**Güvenlik:** None / Anonymous (TIA Portal'da yapılandırılmış)

---

## Değişiklikler

### 1. `scada-reporter/backend/.env`
```
OPC_UA_URL=opc.tcp://192.168.112.50:4840
OPC_UA_USERNAME=
OPC_UA_PASSWORD=
```

### 2. `scada-reporter/backend/app/collector/opc_client.py`
- `browse_tags` varsayılan node_id: `ns=2;s=.` (KEPServerEX) → `ns=0;i=85` (OPC UA Objects klasörü — S7-1500 standart)
- `connect()` zaten cert gerektirmiyor; `set_user`/`set_password` sadece `OPC_UA_USERNAME` doluysa çağrılıyor — değişmez
- Docstring: "KEPServerEX tag agacini tarar" → "S7-1500 OPC UA tag agacini tarar"

### 3. `scada-reporter/backend/app/api/tags.py`
- `browse_tags` docstring: "KEPServerEX tag ağacını tarar" → "S7-1500 OPC UA tag ağacını tarar"

### 4. `scada-reporter/backend/app/models/tag.py`
- `channel` column comment: "KEPServer channel" → "OPC UA channel/group"

### 5. `scada-reporter/frontend/src/pages/Tags.tsx` — 3 satır
| Satır | Eski | Yeni |
|-------|------|------|
| 61 | `KEPServerEX taranıyor...` | `S7-1500 OPC UA taranıyor...` |
| 65 | `KEPServerEX'te None güvenlik modunu etkinleştirin.` | `TIA Portal'da OPC UA sunucusunu etkinleştirin (port 4840).` |
| 117 | `OPC Tara ile KEPServerEX'ten tag seçin` | `OPC Tara ile S7-1500'den tag seçin` |

---

## Dokunulmayan Dosyalar

- `gen_cert.py` — KEPServerEX'e özgü, ama zarar vermiyor; silinmesi ayrı karar
- `certs/` klasörü — kullanılmayacak, silmek ayrı karar
- `config.py` — `OPC_UA_USERNAME`/`OPC_UA_PASSWORD` alanları S7-1500'de de kullanılabilir (opsiyonel auth), değişmez

---

## Doğrulama

1. Backend başlat: `just run-backend`
2. `GET /tags/browse` endpoint'i çağır (Swagger UI: `http://localhost:8001/docs`)
3. S7-1500'e bağlanabilirse tag listesi döner
4. Bağlanamazsa: PLC'de TIA Portal → PLC Properties → OPC UA → Server → "Activate OPC UA Server" kontrol et, port 4840 güvenlik duvarı açık mı kontrol et
