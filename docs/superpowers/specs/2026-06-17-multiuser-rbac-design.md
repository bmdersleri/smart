# Çok Kullanıcılı RBAC + Kullanıcı İşlemleri Menüsü — Tasarım

**Tarih:** 2026-06-17
**Branch:** feat/i18n-multilanguage (veya yeni feat/multiuser-rbac)
**Durum:** Onaylandı (tasarım), implementation plan bekliyor

## Amaç

Projede birden fazla kullanıcı admin tarafından tanımlanabilsin. Kullanıcı
yetkileri (yeni tag ekleme, PLC ekle/düzenle/sil, rapor şablonu
oluştur/değiştir/sil) "Kullanıcı İşlemleri" menüsü üzerinden yönetilsin. Dil
seçeneği zaten kişisel ayar olarak mevcut.

## Mevcut Durum

- `User` modeli: `id, username, email, hashed_password, full_name, role
  (admin/operator/viewer), language, is_active, created_at`.
- `require_role(*roles)` dependency var; tags.py (import/create) ve
  advanced_reports.py'de kullanılıyor.
- **Güvenlik açıkları (bu işle düzeltilecek):**
  - `/auth/register` açık — kimlik doğrulamasız herkes kayıt olabiliyor.
  - PLC create/update/delete sadece `get_current_user` ile korunuyor — herhangi
    bir giriş yapmış kullanıcı PLC CRUD yapabiliyor.
- Kullanıcı yönetimi API/UI yok (liste, oluştur, rol/yetki düzenle, şifre
  sıfırla, aktif/pasif, sil).
- Frontend `AuthContext` `role`'ü biliyor ama rol bazlı UI gating yok.

## Yetki Modeli (Hibrit: rol + kullanıcı override)

**Efektif yetki = rol varsayılanı, kullanıcı override varsa onunla ezilir.**

### Yetki kataloğu (orta granülerlik)

- `tag:create`
- `plc:manage` (ekle/düzenle/sil birlikte)
- `report_template:create`
- `report_template:edit`
- `report_template:delete`

(Kullanıcı yönetimi ayrı bir yetki anahtarı değil; `role == "admin"` ile gelir.)

### Rol varsayılanları (kod sabiti — `ROLE_DEFAULTS`)

| Yetki | admin | operator | viewer |
|---|---|---|---|
| `tag:create` | ✅ | ✅ | ❌ |
| `plc:manage` | ✅ | ✅ | ❌ |
| `report_template:create` | ✅ | ✅ | ❌ |
| `report_template:edit` | ✅ | ✅ | ❌ |
| `report_template:delete` | ✅ | ❌ | ❌ |
| kullanıcı yönetimi | ✅ | ❌ | ❌ |

- `admin` rolü her zaman tüm yetkilere + kullanıcı yönetimine sahip; override
  ile **kısıtlanamaz**.
- Override yalnız `operator`/`viewer` için anlamlıdır.

### Override depolama

- `User.permission_overrides`: JSON kolonu, default `{}`.
- Format: `{"<perm_key>": bool}` — `true` = yetkiyi ekle, `false` = yetkiyi çıkar.
- Örnek: `{"plc:manage": false, "report_template:delete": true}`.
- Efektif hesap: `eff = ROLE_DEFAULTS[role].copy()`; her override için
  `eff[key] = value`. admin için override yok sayılır (her zaman tam set).

## Veri Modeli Değişikliği

`User` modeline tek kolon eklenir:

```python
permission_overrides: Mapped[dict] = mapped_column(
    JSON, default=dict, server_default="{}", nullable=False
)
```

Alembic migration ile eklenir. Mevcut kolonlar değişmez. SQLite (dev/test) ve
PostgreSQL (prod) JSON tipini destekler.

## Backend

### Yeni: `app/core/permissions.py`

- `ALL_PERMISSIONS: tuple[str, ...]` — geçerli yetki anahtarları.
- `ROLE_DEFAULTS: dict[str, dict[str, bool]]` — yukarıdaki matris.
- `effective_permissions(user: User) -> set[str]` — admin ise tüm set; aksi
  halde rol default + override birleşimi.
- `user_can(user: User, perm: str) -> bool`.

### Yeni dependency: `require_perm(perm)` (auth.py)

```python
def require_perm(perm: str):
    async def _check(user: User = Depends(get_current_user)):
        if not user_can(user, perm):
            raise HTTPException(status_code=403, detail="Yetki yok")
        return user
    return _check
```

`require_role` korunur (admin-only rotalarda kullanılır).

### Endpoint koruma güncellemeleri

- `tags.py` create → `require_perm("tag:create")` (mevcut `require_role` yerine).
  Import endpoint'i admin/operator `require_role` olarak kalabilir veya
  `tag:create`'e taşınır (plan kararı; default: `tag:create`).
- `plc.py` create/update/delete → `require_perm("plc:manage")` (**güvenlik
  düzeltmesi** — şu an korumasız).
- Rapor şablonu create/edit/delete → ilgili `require_perm(...)`.
- `/auth/register` → `require_role("admin")` (artık açık değil).

### Yeni: `app/api/users.py` (`/api/users`, hepsi `require_role("admin")`)

- `GET /` — kullanıcı listesi: `id, username, full_name, email, role,
  is_active, permissions (efektif liste)`.
- `POST /` — oluştur: `username, email, password, full_name, role,
  permission_overrides?`. Username/email benzersiz kontrolü.
- `PATCH /{id}` — güncelle: `full_name, email, role, is_active,
  permission_overrides` (kısmi). Son admin'in rol/aktiflik düşürülmesi engellenir.
- `POST /{id}/password` — admin şifre sıfırlar (`{ "password": "..." }`).
- `DELETE /{id}` — sil. Son admin silinemez; admin kendini silemez.

### `/auth/me` genişletme

- `GET /auth/me` yanıtına `permissions: list[str]` (efektif) eklenir.
- `PATCH /auth/me` — mevcut dil değişimi korunur; kendi şifre değişimi eklenir
  (`{ "current_password": "...", "new_password": "..." }` opsiyonel alanlar).

### Son-admin koruması (invariant)

DELETE ve PATCH (role/is_active değişiminde) öncesi: aktif admin sayısı > 1
değilse son admin'i düşüren işlem 400 ile reddedilir.

## Frontend

- `AuthContext.User`'a `permissions: string[]`; `can(perm: string): boolean`
  helper context'ten sağlanır.
- **Yeni sayfa `pages/Users.tsx`** — "Kullanıcı İşlemleri" menüsü, yalnız
  `role === "admin"` görür:
  - Kullanıcı tablosu (username, ad, rol, aktif, yetkiler).
  - Oluştur/Düzenle modal: rol seçimi + override checkbox'ları (yetki kataloğu),
    canlı efektif yetki gösterimi.
  - Şifre sıfırla aksiyonu.
  - Aktif/pasif toggle + sil (son admin korumalı, UI'da disable + sunucu 400).
- **UI gating**: tag-ekle, PLC-CRUD, rapor-şablon butonları `can(...)` ile
  gizlenir/disable. Sunucu zaten 403 verir — UI kozmetik katman.
- Menü/yönlendirme: admin'e "Kullanıcı İşlemleri" nav linki.
- Tüm yeni string'ler i18n (en/tr/ru/de), mevcut react-i18next düzenine uyar.

## Test (TDD)

### Backend (pytest async)

- `permissions.py` birim: rol default matrisi, override ekle/çıkar, admin tam
  set, geçersiz perm.
- `users` API: CRUD happy path, username/email çakışma, yetkisiz erişim 403
  (operator/viewer), son-admin silme/düşürme 400, kendini silme engeli.
- Enforcement: `tag:create`, `plc:manage`, `report_template:*` rotalarında
  yetkisiz 403 / yetkili 2xx.
- `/auth/register` admin olmadan 403.
- `/auth/me` `permissions` döner; kendi şifre değişimi.

### Frontend

- `can()` gating: yetkisiz kullanıcıda buton yok/disable.
- Users sayfası: admin render, non-admin erişim engeli, override checkbox →
  PATCH çağrısı.

## Kapsam Dışı (YAGNI)

- Yetki grupları/takımlar, özel rol oluşturma (sadece 3 sabit rol).
- Audit log / yetki değişim geçmişi.
- E-posta ile şifre sıfırlama akışı (sadece admin manuel reset).
- SSO/OAuth harici sağlayıcı.

## Açık Notlar

- Operatör default yetkileri onaylandı (rapor silme hariç hepsi).
- Şifre kuralları: plan aşamasında min uzunluk (≥6) basit kontrol eklenebilir;
  karmaşıklık zorunluluğu kapsam dışı.
