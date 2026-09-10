# production-sync

HR botining **barqaror eksport jadvali** (`production_sync_events`) orqali
bajarilgan ishlab chiqarish/brak hodisalarini Ombor moduliga
(`POST /production-batches`, W4 kontrakti) avtomatik yuboruvchi kichik
ko'prik xizmati.

To'liq kontekst: `abc2019/inventory` repo'sidagi
`docs/erp_integration_plan.md` (bo'lim 5).

## Arxitektura tarixi (qisqacha)

Bu xizmat ikki marta katta qayta qurishdan o'tdi:

1. **v1**: HR'ning ichki `task_quantity_logs` jadvalidan to'g'ridan-to'g'ri
   o'qib, matnni (`erp_bridge_kit.best_name_match`) mahsulotga moslashtirar
   edi. Muammo: HR'ning ichki sxemasi tez-tez o'zgarib turgani sababli
   (boshqa dasturchi/AI tomonidan faol rivojlantirilgan), integratsiya
   muntazam buzilib turdi — bir marta hatto qadoqlash vazifalari
   (banka yuvish, stiker) tasodifan mahsulotlarga "eng yaqin" deb
   moslashtirilib yuborilgan edi.
2. **v2 (hozirgi)**: HR o'zi maxsus, BARQAROR `production_sync_events`
   jadvalini yuritadi va aniq `ombor_external_code` + `completed_units`
   (dona) beradi. **Fuzzy matching va birlik konvertatsiyasi butunlay
   olib tashlandi** — endi bu xizmat faqat kodni Ombor'ning UUID'iga
   aylantirib, to'g'ridan-to'g'ri yuboradi.

## Qanday ishlaydi

1. Har `POLL_INTERVAL_SECONDS` (standart 300) soniyada HR'ning
   `GET /internal/production-sync-events?since_id=&limit=` endpointini
   so'raydi (sahifalab, barcha yangi yozuvlarni yig'ib oladi).
2. Har bir hodisaning `operation_key`i — HR'ning o'z idempotentlik kaliti;
   mahalliy holat bazasida (`processed_entries`) "allaqachon ko'rilganmi"
   tekshiriladi (faqat `SYNCED` chetlab o'tiladi, `FAILED` qayta uriniladi).
3. `ombor_external_code`ni Ombor'ning `GET /products/by-code/{code}` orqali
   UUID'ga aylantiradi (bitta tsikl davomida bir xil kod uchun keшlanadi).
4. Ombor'ning `POST /production-batches`iga `source_id=hr-event:{operation_key}`,
   `completed_units`, va `event_type` (`PRODUCED` yoki `DEFECT`) bilan
   yuboradi (idempotent).
5. `DEFECT` — bu tuzatish (REVERSAL) EMAS, balki haqiqiy voqea: mahsulot
   to'g'ri ishlab chiqarilgan edi, lekin keyinroq bir qismi nuqsonli
   topildi. Ombor tarafida faqat tayyor mahsulot qoldig'ini kamaytiradi,
   xomashyoga tegmaydi (W4'da qurilgan).
6. Kod Ombor'da topilmasa yoki Ombor vaqtincha ishlamasa → `FAILED`,
   keyingi tsiklda **avtomatik qayta uriniladi**.

## Xato tuzatish qanday ishlaydi

HR'da xato yozilgan taqdirda (noto'g'ri mahsulot/miqdor) — bu
`production_sync_events` orqali avtomatik tuzatilmaydi (ataylab —
REVERSAL/ADJUSTMENT mantig'i xatolar KAM bo'lgani uchun qasddan olib
tashlangan). Tuzatish Ombor'da **owner tomonidan qo'lda**,
`POST /transactions` (`INVENTAR_FARQI` turi) orqali amalga oshiriladi.

## Sozlash

`.env.example`ga qarang:

- `HR_INTERNAL_API_BASE_URL` / `HR_INTERNAL_API_TOKEN` — HR xizmatidagi
  bilan bir xil bo'lishi kerak.
- `OMBOR_API_BASE_URL` — Ombor xizmatining manzili.
- `PRODUCT_CODE_MAP`, `UNIT_MULTIPLIERS`, `MATCH_THRESHOLD` — **endi kerak
  emas** (HR o'zi aniq kod va dona sonini beradi).

## Ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # to'ldiring
python -m app.main
```

## Testlar

```bash
pip install -r requirements.txt
pytest -q
```

22 test: HR reader (HTTP orqali, mock transport bilan tarmoqsiz),
holat bazasi, orchestratsiya (PRODUCED/DEFECT to'g'ri yuborilishi, kod
keшlanishi, noma'lum kod xavfsiz FAILED bo'lib qayta urinilishi, Ombor
xatosidan keyin qayta tiklanish, takroriy qayta ishlanmaslik, sahifalab
o'qish, Ombor sozlanmaganda xavfsiz to'xtash).

## Deploy (Railway)

HR botidan alohida Railway xizmati sifatida deploy qilinadi (fayl emas,
tarmoq orqali gaplashadi). `STATE_DATABASE_PATH` uchun Railway Volume
tavsiya etiladi — aks holda har qayta deployda holat yo'qolib, hodisalar
qayta tekshiriladi (zararsiz, chunki Ombor tarafida ham idempotent, lekin
ortiqcha ish).
