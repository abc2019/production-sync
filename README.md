# production-sync

HR botining bajarilgan tasklarini (`plan_tasks` + `task_quantities`) Ombor
moduliga (`POST /production-batches`, W4 kontrakti) avtomatik yuboruvchi
kichik ko'prik xizmati.

To'liq kontekst: `abc2019/inventory` repo'sidagi
`docs/erp_integration_plan.md` (bo'lim 5).

## Qanday ishlaydi

1. HR botining SQLite bazasidan **faqat o'qish** rejimida (`mode=ro&immutable=1`)
   ulanadi — HR'ning kodiga yoki bazasiga hech qanday yozuv qilinmaydi.
2. **`task_quantity_logs`** jadvalidan o'qiydi (`plan_tasks`/`task_quantities`
   emas — ular joriy holatning o'zgaruvchan yig'indisi, `task_quantity_logs`
   esa HR botining o'zi ishlatadigan O'ZGARMAS hisobot jurnali).
3. Har bir qatorning `operation_key`i (HR botining o'z idempotentlik
   kaliti) — bizning `source_id`imizning asosi. Shu bilan bir xil hisobot
   ikki marta yuborilmaydi, va bitta task uchun bir necha alohida hisobot
   bo'lsa (masalan ish kuni davomida ikki marta miqdor kiritilsa), har
   biri alohida, to'g'ri qayta ishlanadi.
4. Har bir hisobot matnini (`task_text`) Ombor katalogidagi (faqat
   `FINISHED`, faqat `external_code`i bor) mahsulotlar bilan solishtiradi
   (`erp_bridge_kit.best_name_match`).
5. Ishonchli moslik topilsa → Ombor'ning `POST /production-batches`iga
   `source_id=hr-op:{operation_key}` bilan yuboradi (idempotent).
6. Moslik noaniq bo'lsa (yoki umuman topilmasa) → **hech qachon avtomatik
   yozilmaydi** — mahalliy holat bazasida `NEEDS_REVIEW` sifatida saqlanadi.
7. Ombor vaqtincha ishlamay qolsa → `FAILED`, keyingi tsiklda **avtomatik
   qayta uriniladi** (faqat `SYNCED` yozuvlar butunlay chetlab o'tiladi).

## ⚠️ Productionga chiqarishdan oldin tasdiqlash kerak

- ~~HR'ning "bajarilgan" belgisi~~ — **hal qilindi**: HR'ning haqiqiy
  kodini (`abc2019/ShohonaWorkBot/db.py`) o'qib tasdiqlandi — `status`
  qiymatlari `'pending'`/`'done'`/`'not_done'` (`'completed'` emas), va
  eng ishonchli manba sifatida `task_quantity_logs` (o'zgarmas jurnal)
  tanlandi, `plan_tasks.status`ga bog'liq bo'lmasdan.
- **`completed_qty` / `unit="box"`ning Ombor birligiga nisbati — HALI
  TASDIQLANMAGAN.** HR kodida "box" (quti) qattiq belgilangan birlik,
  lekin bitta "box" nechta Ombor birligiga (banka) yoki nechta partiyaga
  (300) tengligi HR/CEO tomonidan aytilishi kerak — kodda bunday
  konvertatsiya konstantasi topilmadi. Hozircha `completed_qty` **xom
  holda**, o'zgarishsiz `batch_count` sifatida yuborilmoqda — bu, ehtimol,
  noto'g'ri. Aniqlangach `app/sync.py`da bitta qatorni (`batch_count=`)
  konvertatsiya bilan almashtirish kerak bo'ladi.
- **Haqiqiy HR bazasiga ulanib sinalmagan** — faqat HR'ning haqiqiy
  sxemasiga mos soxta (fake) baza bilan testlangan (`tests/conftest.py`).
  Real muhitda birinchi marta ishga tushirishdan oldin, kichik
  `HR_DATABASE_PATH`ning **nusxasi** (production emas) bilan tekshirib
  ko'rish tavsiya etiladi.

## Ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# HR_DATABASE_PATH, OMBOR_API_BASE_URL va h.k.ni to'ldiring

python -m app.main
```

`OMBOR_API_BASE_URL` bo'sh qoldirilsa, xizmat hech narsa qilmaydi (xavfsiz
standart holat) — tasodifan yarim sozlangan holda ishga tushib qolmasligi
uchun.

## Testlar

```bash
pip install -r requirements.txt
pytest -q
```

21 test: HR reader (faqat o'qish, filtrlash, tartiblash), holat bazasi
(SYNCED chetlab o'tiladi, FAILED/NEEDS_REVIEW qayta uriniladi),
orchestratsiya (moslik topilganda push, noaniq bo'lganda review,
xomashyo hech qachon tanlanmasligi, Ombor xatosidan keyin qayta tiklanish,
takroriy qayta ishlanmaslik, Ombor sozlanmaganda xavfsiz to'xtash).

## Deploy (Railway)

`Procfile` va HR bazasiga qanday ulanish (Railway volume yoki boshqa
usul bilan) muhitga bog'liq — `HR_DATABASE_PATH` shu joyni ko'rsatishi
kerak. `STATE_DATABASE_PATH` uchun ham doimiy saqlanadigan joy (volume)
tavsiya etiladi — aks holda har qayta deployda holat yo'qolib, tasklar
qayta tekshiriladi (zararsiz, chunki Ombor tarafida ham idempotent, lekin
ortiqcha ish).
