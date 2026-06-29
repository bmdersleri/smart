# Tesis Değişkenleri — Operatör Geçiş Kılavuzu

**Sistem:** EKONT SMART REPORT — Su/atıksu arıtma SCADA veri toplama ve raporlama
**İlgili Plan:** Plan 5 — Seed'ler + `gunluk_rapor` çalışma kitabı → değişken geçişi
**Son gözden geçirme:** `app/seed_facility_variables.py`, `app/seed_excel_template.py`

---

## İçindekiler

1. [Önkoşullar](#1-önkoşullar)
2. [Temel Değişkenler Tablosu](#2-temel-değişkenler-tablosu)
3. [Ortam Değişkenleri](#3-ortam-değişkenleri)
4. [Gerçek Çalışma Kitabını Ekleme](#4-gerçek-çalışma-kitabını-ekleme)
5. [Çalıştırma Sırası](#5-çalıştırma-sırası)
6. [Zorunlu Doğrulama](#6-zorunlu-doğrulama)

---

## 1. Önkoşullar

**`just seed-catalog` önce çalışmış olmalıdır.**

`seed-facility-variables` ve `seed-excel-template` scriptleri değişken
formüllerinde kaynak olarak gerçek PLC tag'larını referans alır. Tag kataloğu
veritabanında mevcut değilse değişken kaydı başarısız olur.

Kontrol:

```bash
just seed-catalog        # tag kataloğunu yükle
just seed-facility-variables   # tesis değişkenlerini oluştur
just seed-excel-template       # Excel şablonunu bağla (ayrıca çalıştırılır)
```

> **Not:** `just seed` (bileşik) artık `seed-facility-variables` adımını da içerir.
> `seed-excel-template`, taahhüt edilmiş çalışma kitabı gerektirdiğinden bileşik
> recipe'ye **eklenmemiştir** — her zaman ayrıca çalıştırılmalıdır.

---

## 2. Temel Değişkenler Tablosu

Aşağıdaki değişkenler `seed-facility-variables` tarafından oluşturulur.

| Kod | Anlamı | Kaynak tip | Toplam sayaç yöntemi |
|-----|--------|------------|---------------------|
| `terfi1_debi_gunluk` | Terfi 1 Çıkış Debi (Günlük) | `tag` — `gtuTP02DB01.GUNLUK` | `last` — günlük sıfırlamalı sayaç |
| `terfi2_debi_gunluk` | Terfi 2 Çıkış Debi (Günlük) | `tag` — `gtuTP01DB01.GUNLUK` | `last` — günlük sıfırlamalı sayaç |
| `aot_giris_debi_gunluk` | AOT günlük giriş debisi (terfi1 + terfi2 toplamı) | `expression` — `terfi1 + terfi2` | toplama (`last` bileşenlerden) |
| `baat_giris_debi_gunluk` | BAAT günlük giriş debisi (ölçülen) | `tag` — `SEED_BAAT_GIRIS_NODE_ID` ile belirlenir | `last` — günlük sıfırlamalı sayaç |
| `tesis_toplam_debi_olculen_gunluk` | Ölçülen toplam tesis debisi (GENEL_TOPLAM_DEBI günlük delta'sı) | `tag` — `GENEL_TOPLAM_DEBI` | `delta` — kümülatif sayaç |
| `tesis_toplam_debi_hesaplanan_gunluk` | Hesaplanan toplam tesis debisi (AOT + BAAT + kapasite) | `ref` — bileşik | toplama |
| `giris_7gun_ort_debi` | Son 7 günlük ortalama giriş debisi | `expression` — kayan pencere | ortalama |

### Toplam sayaç semantiği

- **`last`** → tag günlük sıfırlanır; günün son değeri o günün toplamıdır.
  `*.GUNLUK` tag adı kuralına uyan tag'lar bu kategoriye girer.
- **`delta`** → tag kümülatif artar; günlük değer = gün sonu − gün başı.
  `GENEL_TOPLAM_DEBI` bu davranışa sahip **varsayılmıştır**.
  Eğer bu tag da günlük sıfırlanıyorsa `last` olarak değiştirin (bkz. §6).

---

## 3. Ortam Değişkenleri

Seed scriptleri iki isteğe bağlı ortam değişkeni okur:

| Değişken | Açıklama | Örnek |
|----------|----------|-------|
| `SEED_BAAT_GIRIS_NODE_ID` | BAAT giriş debisi tag'ının `tag_id` değeri (veya OPC UA node-id). Ayarlanmazsa script bu değişkeni atlar ve bir uyarı loglar. | `SEED_BAAT_GIRIS_NODE_ID=ns=2;i=1042` |
| `SEED_AOT_DESIGN_CAPACITY_M3` | AOT tasarım kapasitesi (m³/gün). Kapasite bazlı hesaplanan debi formülünde kullanılır. Varsayılan: `0` (kapasite terimi ihmal edilir). | `SEED_AOT_DESIGN_CAPACITY_M3=5000` |

`.env` dosyanıza ekleyin:

```bash
# Tesis değişkenleri seed parametreleri
SEED_BAAT_GIRIS_NODE_ID=ns=2;i=1042
SEED_AOT_DESIGN_CAPACITY_M3=5000
```

---

## 4. Gerçek Çalışma Kitabını Ekleme

Varsayılan `seed-excel-template` sentetik bir örnek şablonla çalışır.
Üretim raporunu değişken bağlamalarıyla eşleştirmek için:

### Adım 4.1 — Çalışma kitabını depoya ekleyin

```bash
# Gerçek rapor Excel dosyasını aşağıdaki konuma kopyalayın:
scada-reporter/backend/app/seed_data/gunluk_rapor.xlsx
```

```bash
git add scada-reporter/backend/app/seed_data/gunluk_rapor.xlsx
git commit -m "chore(seed-data): commit real gunluk_rapor.xlsx for excel template seeding"
```

### Adım 4.2 — `SHEET_META` ve `COLUMN_BINDINGS` düzenleyin

`app/seed_excel_template.py` içindeki sabitler gerçek çalışma sayfası geometrisine
göre ayarlanmalıdır:

```python
# app/seed_excel_template.py — düzenlenecek bölümler

SHEET_META = dict(
    sheet_name="Günlük Rapor",   # ← gerçek sekme adı
    header_row=3,                # ← başlık satırı (1-tabanlı)
    date_col="A",                # ← tarih sütunu (date_col, date_column değil)
    data_start_row=4,            # ← veri başlangıç satırı
    date_mode="write",           # ← "write" veya "read"
)

COLUMN_BINDINGS: list[tuple[str, str]] = [
    # (excel_sütunu, değişken_kodu)
    ("E", "aot_giris_debi_gunluk"),
    ("F", "kapasite_fazlasi_gunluk"),
    ("K", "baat_giris_debi_gunluk"),
    ("M", "tesis_toplam_debi_hesaplanan_gunluk"),
]
```

Gerçek çalışma kitabınızdaki sütun harflerini ve satır numaralarını doğrulayın;
yukarıdaki değerler referans örneğe dayanmaktadır.

---

## 5. Çalıştırma Sırası

```bash
# 1. Tag kataloğunu yükle (henüz yapılmadıysa)
just seed-catalog

# 2. Tesis değişkenlerini oluştur
just seed-facility-variables

# 3. Excel şablonunu değişken bağlamalarıyla eşleştir
just seed-excel-template
```

Tüm adımlar kendi kendine idempotentdir (birden fazla çalıştırma güvenlidir).
Mevcut bir değişken tekrar seeded edilirse script kaydı atlar ve bir uyarı loglar.

---

## 6. Zorunlu Doğrulama

**Oluşturulan herhangi bir raporu güvenmeden önce bu adımı tamamlayın.**

### 6.1 Ön koşul

Plan-4 önizleme arayüzü aktif ve erişilebilir olmalıdır (geliştirme sunucusu
çalışıyor: `just dev`).

### 6.2 Her değişken için kontrol

1. Yönetici panelinden **Değişkenler** sayfasına gidin.
2. Her seeded değişkeni açın.
3. Bilinen bir gün (veri olduğu kesinlikle bilinen bir tarih) seçin.
4. Değerin makul olduğunu doğrulayın:

   | Değişken | Beklenen aralık | Anormallik işareti |
   |----------|----------------|-------------------|
   | `terfi1_debi_gunluk` | > 0 m³/gün, AÖT/BAAT transfer kapasitesi içinde makul | 0 → `gtuTP02DB01.GUNLUK` tag'i okunmuyor |
   | `terfi2_debi_gunluk` | > 0 m³/gün, AÖT/BAAT transfer kapasitesi içinde makul | 0 → `gtuTP01DB01.GUNLUK` tag'i okunmuyor |
   | `aot_giris_debi_gunluk` | > 0 m³/gün, tesisin kapasitesine göre | 0 veya çok büyük değer |
   | `baat_giris_debi_gunluk` | > 0 m³/gün | `SEED_BAAT_GIRIS_NODE_ID` ayarlanmadıysa boş |
   | `tesis_toplam_debi_olculen_gunluk` | > 0 m³/gün, günlük üretimle uyumlu | Ölçülen toplam debi, GENEL_TOPLAM_DEBI sayacının günlük delta'sı; pozitif ve günlük üretimle uyumlu olmalı. Negatif → gün başı/sonu sıralamasını kontrol edin |
   | `tesis_toplam_debi_hesaplanan_gunluk` | ≈ aot + baat + kapasite fazlası; işaret pozitif, büyüklük makul olmalı | Yalnızca `SEED_BAAT_GIRIS_NODE_ID` + `SEED_AOT_DESIGN_CAPACITY_M3` ayarlıysa oluşur; yoksa değişken yoktur |
   | `giris_7gun_ort_debi` | 7 günlük ortalama, yaklaşık günlük değerlere yakın | Tuhaf sapma → pencere hesabı kontrol |

### 6.3 Toplam sayaç semantiği anormallik tespiti

**`tesis_toplam_debi_olculen_gunluk` için en sık yapılan ayarlama:**

`tesis_toplam_debi_olculen_gunluk`, `GENEL_TOPLAM_DEBI` kümülatif totalizerinin günlük delta'sıdır.

- Değer tesisin toplam günlük üretiminden büyük büyüklük sırasıyla **fazla** ise:
  tag kümülatif değil günlük sıfırlanıyor demektir — `delta` yerine `last` kullanın.

  `app/seed_facility_variables.py` içinde:
  ```python
  # Şu an:
  _agg(genel, "delta")
  # Değiştir:
  _agg(genel, "last")
  ```
  Sonra `just seed-facility-variables` tekrar çalıştırın.

- Değer **negatif** çıkıyorsa: gün başı/sonu sıralamayı kontrol edin.

### 6.4 Excel şablon sütun bağlaması kontrolü

`just seed-excel-template` çalıştırıldıktan sonra:

1. **Raporlar** sayfasından günlük rapor şablonuyla bir ön izleme oluşturun.
2. Excel/PDF çıktısındaki değerleri doğrudan veritabanı sorgusuyla karşılaştırın.
3. Sütun kaymalarını tespit etmek için birkaç farklı tarihi test edin.

---

## Sorun Giderme

| Belirti | Olası neden | Çözüm |
|---------|-------------|-------|
| `seed-facility-variables` — "tag not found" hatası | Catalog seeded edilmemiş | `just seed-catalog` çalıştırın |
| `baat_giris_debi_gunluk` değişkeni oluşturulmadı | `SEED_BAAT_GIRIS_NODE_ID` eksik | `.env` dosyasına ekleyin |
| `seed-excel-template` — dosya bulunamadı | `gunluk_rapor.xlsx` depoya eklenmemiş | §4.1 adımını takip edin |
| Önizlemede tüm değerler 0 | Tarih aralığında veri yok | Farklı tarih seçin veya poller çalışıyor mu kontrol edin |
| `tesis_toplam_debi_olculen_gunluk` beklenmedik büyük | `delta` vs `last` semantiği | §6.3 talimatlarını izleyin |
