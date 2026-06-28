# Tailwind v4 — Renk Sistemi @theme Token Migration (Follow-up)

**Durum:** PLANLANDI (yürütülmedi). Mekanik v4 utility göçü + animasyon @theme token'ı
`ba69730`'da shipping edildi. Bu doküman geriye kalan riskli parçayı tanımlar.

## Sorun

`frontend/src/index.css` light/dark temayı v4-karşıtı şekilde yapıyor:

- `@theme` ile **renk token'ı yok**. `@custom-variant dark` yok. `dark:` variant = 0 kullanım.
- Light tema, üretilen utility'leri elle ezerek kuruluyor:
  `html.light .bg-gray-900\/60 { background-color: ... }` — ~190 satır, ~40 selector.
- Her yeni shade/opacity kombosu **elle aynalanmak** zorunda (bkz. dev
  `bg-green-900\/50, \/40, \/30` enumerasyonları). Kırık değil ama kırılgan ve büyümez.

## Hedef (v4-idiomatik)

```css
@theme {
  --color-surface:        … ;   /* bg-gray-950 yerine */
  --color-surface-raised: … ;   /* bg-gray-900 */
  --color-surface-sunken: … ;   /* bg-gray-800 */
  --color-border-subtle:  … ;
  --color-text-primary:   … ;   /* text-white */
  --color-text-muted:     … ;   /* text-gray-400 */
  /* accent renkleri (cyan/blue/emerald/red/amber) v4 default paletten kalır */
}
@custom-variant dark (&:where(.dark, .dark *));
```

Component'ler `bg-gray-900` yerine `bg-surface-raised`, `text-gray-400` yerine
`text-muted` kullanır. Token'lar light/dark için `:root` ve `.dark` (veya `.light`)
altında bir kez tanımlanır → tek yerden çevirme, elle utility-override biter.

## Neden tek seferde yapılmadı

- ~30 component, yüzlerce `bg-gray-*/text-gray-*/border-gray-*` kullanımı.
- Her biri semantic token'a map edilmeli; opacity modifier'lı varyantlar
  (`bg-gray-900/60`) token + `/60` ile yeniden ifade edilmeli.
- Görsel regresyon riski yüksek — her sayfa light+dark'ta QA gerektirir.

## Önerilen artımlı yol

1. `@theme` token + `@custom-variant` ekle (additive, mevcut override'lar dururken).
2. Bir semantic katman seç (önce yüzeyler: surface/border), token utility'lerini tanımla.
3. Sayfa sayfa migrate et; her sayfadan sonra Playwright ile light+dark snapshot karşılaştır.
4. Bir kategori (ör. yüzeyler) tüm component'lerde bitince, `index.css`'teki
   karşılık gelen `html.light` override bloklarını sil.
5. Metin → kenarlık → rozet renkleri sırayla tekrarla.
6. Tüm kategoriler bitince `html.light` override CSS'i tamamen kaldır; tema sadece
   token + `dark`/`light` variant ile çalışsın.

## Kapsam dışı / korunur

- Accent palet (cyan/blue/emerald/red/amber/indigo) v4 default — dokunma.
- Animasyonlar zaten `@theme --animate-flip-in` + inline (dinamik delay) — tamam.
- frser-sqlite Grafana, backend: ilgisiz.
