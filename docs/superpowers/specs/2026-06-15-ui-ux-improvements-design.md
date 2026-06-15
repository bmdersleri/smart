# UI/UX İyileştirmeleri — Tasarım Dokümanı

**Tarih:** 2026-06-15
**Kapsam:** Dashboard, Tag Yönetimi, Trend Grafik, Raporlar
**Kullanıcılar:** Saha operatörleri (24/7 izleme) + tesis müdürleri (raporlar)

---

## 1. Backend Değişiklikleri

### 1.1 Tag Modeli Genişletme

`scada-reporter/backend/app/models/tag.py` — iki opsiyonel alan eklenir:

```python
min_alarm: float | None = None
max_alarm: float | None = None
```

- Alembic migration ile mevcut tag'lere `NULL` atanır (alarm yok)
- `PATCH /api/tags/{id}` endpoint'i eklenir — kısmi güncelleme (birim, cihaz, kanal, min_alarm, max_alarm)

### 1.2 Dashboard Current-Values Yanıtı

`GET /api/dashboard/current-values` response'una `alarm_state` alanı eklenir:

```python
alarm_state: Literal["overflow", "min", "max"] | None
```

Hesaplama mantığı (backend):
- Değer `> 1_000_000` veya kalite kötüyse → `"overflow"`
- `max_alarm` tanımlı ve değer `> max_alarm` → `"max"`
- `min_alarm` tanımlı ve değer `< min_alarm` → `"min"`
- Aksi → `None`

### 1.3 ReportHistory Tablosu (Yeni)

```python
class ReportHistory(Base):
    __tablename__ = "report_history"
    id: int (PK)
    created_at: datetime
    tag_ids: str  # JSON array
    start: datetime
    end: datetime
    interval: str  # "hourly" | "daily"
    format: str    # "excel" | "json"
    file_path: str # backend/reports/<uuid>.<ext>
```

Yeni endpoint'ler:
- `POST /api/reports/generate` — mevcut davranış + history kaydı + dosya diske yazılır
- `GET /api/reports/history` — son 10 kaydı döner
- `GET /api/reports/history/{id}/download` — kaydedilmiş dosyayı döner

Dosyalar `backend/reports/` dizininde saklanır. 10'dan fazla kayıt olunca en eski silinir (dosya + DB kaydı).

---

## 2. Dashboard

### 2.1 Alarm Bandı

Stat kartların üstüne, yalnızca `alarm_state !== null` olan tag varsa gösterilir:

```
🔴 2 ALARM  |  Havuz_Seviye: overflow  ·  Hat1_Debi: max aşımı (3336 > 3000)  [×]
```

- Her alarm adına tıklayınca tabloda o satıra scroll edilir (`scrollIntoView`)
- `[×]` ile bant geçici gizlenir (sayfa yenilenince tekrar görünür)
- Alarm yoksa bant DOM'da yer kaplamaz

### 2.2 Satır Highlight

`alarm_state`'e göre:

| alarm_state | Satır stili | Değer metni |
|-------------|-------------|-------------|
| `"overflow"` | `bg-red-950` arka plan | `OVERFLOW` (kırmızı) |
| `"max"` | `bg-yellow-950` arka plan | Değer kırmızı renk |
| `"min"` | `bg-yellow-950` arka plan | Değer kırmızı renk |
| `null` | Mevcut stil | Mevcut stil |

### 2.3 PLC Bağlantı Stat Kartı

Mevcut 3 stat kartına 4. kart eklenir:

```
PLC BAĞLANTI
● Bağlı
```

- `GET /health` endpoint'ini 10sn'de bir poll eder (`refetchInterval: 10000`)
- `opc_connected: true` → yeşil nokta + "Bağlı"
- `opc_connected: false` → kırmızı + "Kopuk"

---

## 3. Tag Yönetimi

### 3.1 Arama Kutusu

Tablo üstüne input eklenir. Client-side filtre — cihaz adı veya tag adına göre (case-insensitive). Filtre temizlenince tüm liste döner.

### 3.2 Düzenle Modal

Her satıra "Düzenle" butonu eklenir (mevcut "Sil" yanına):

Modal alanları:
| Alan | Tip | Notlar |
|------|-----|--------|
| Ad (node_id) | Text, read-only | PLC adresi değişmemeli |
| Birim | Text | |
| Cihaz | Text | |
| Kanal | Text | |
| Min Alarm | Number, opsiyonel | Boş = alarm yok |
| Max Alarm | Number, opsiyonel | Boş = alarm yok |

Kaydet → `PATCH /api/tags/{id}` → TanStack Query `['tags']` cache invalidate.

Client validasyon: `min_alarm < max_alarm` zorunlu — ikisi de doluysa. Aksi halde "Min değer Max'tan küçük olmalı" hatası gösterilir, istek gönderilmez.

### 3.3 Tablo Değişiklikleri

- Yeni "Alarm" kolonu: `0–5000 mm` veya `—`
- "Sil" butonu metin yerine çöp kutusu ikonu (`🗑`)
- "Düzenle" butonu kalem ikonu (`✏`)

---

## 4. Trend Grafik

### 4.1 Varsayılan Seçim Temizlenir

Sayfa açılınca hiç tag seçili gelmez. Kullanıcı manuel seçer.

### 4.2 Tag Listesi Filtresi

Sol panelin üstüne arama kutusu eklenir. Cihaz/tag adına göre client-side filtre.

### 4.3 Çift Y-Ekseni

Recharts ile:
- İlk seçilen tag'in birimi → sol Y ekseni (`yAxisId="left"`)
- Farklı birimde tag eklenince → sağ Y ekseni aktif (`yAxisId="right"`)
- 3. farklı birim seçilmeye çalışılırsa → toast uyarı: *"Maksimum 2 farklı birim. Önce mevcut bir birimi kaldır."*
- Eksen etiketleri: sol `m³/h`, sağ `bar` (tag'lerin biriminden otomatik alınır)
- Tooltip her satırda birim gösterir

---

## 5. Raporlar

### 5.1 Tag Seçimi Yeniden Düzenlenir

Mevcut chip listesi cihaz gruplarına ayrılır:

```
── Hat1 ──────── [Tümünü Seç]
[Hat1_Debi ✓] [Hat1_Max] [Hat1_Min]

── Havuz ─────── [Tümünü Seç]
[Havuz_Basinc] [Havuz_Seviye]
```

- "Tümünü Seç" → grubun tüm tag'leri toggle (hepsi seçiliyse hepsi kalkar)
- Seçili sayısı gösterilir: `"5 tag seçili"`

### 5.2 "Format ?" Butonu Kaldırılır

Belirsiz buton çıkarılır. Mevcut "Excel İndir" ve "JSON" butonları yeterli.

### 5.3 Rapor Geçmişi Bölümü

Formun altına `GET /api/reports/history` ile dolan liste:

```
── Son Raporlar ──────────────────────────────────────
📄 15.06.2026 22:07  Hat1, Hat2 (6 tag)  |  7 gün  |  Excel   [↓ İndir]
📄 14.06.2026 18:30  Pompa1 (5 tag)      |  Bugün   |  JSON    [↓ İndir]
```

- "↓ İndir" → `GET /api/reports/history/{id}/download`
- Liste yoksa "Henüz rapor oluşturulmadı" gösterilir

---

## Uygulama Sırası

1. **Backend** — migration (min_alarm/max_alarm + report_history), PATCH endpoint, alarm_state hesabı, history API
2. **Dashboard** — alarm bandı + satır highlight + PLC kart
3. **Tag Yönetimi** — arama + düzenle modal + tablo kolonları
4. **Trend Grafik** — varsayılan temizle + filtre + çift Y-ekseni
5. **Raporlar** — grup seçim + Format? kaldır + geçmiş bölümü

Her adım bağımsız commit/test edilebilir. Adım 1 (backend) diğer adımların önkoşuludur.

---

## Kapsam Dışı

- PDF rapor çıktısı (WeasyPrint/GTK kurulumu ayrı iş)
- Rapor zamanlama / otomatik gönderim
- Kullanıcı rol yönetimi UI'ı
- Mobil görünüm optimizasyonu
- Real-time WebSocket push (şu an polling yeterli)
