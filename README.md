# production-sync

HR botining bajarilgan tasklarini (`plan_tasks` + `task_quantities`) Ombor
moduliga (`POST /production-batches`, W4 kontrakti) avtomatik yuboruvchi
kichik ko'prik xizmati.

To'liq kontekst: `abc2019/inventory` repo'sidagi
`docs/erp_integration_plan.md` (bo'lim 5).

## Qanday ishlaydi

1. HR botining **ichki, faqat-o'qish HTTP API'sidan** (`internal_api.py`,
   `abc2019/ShohonaWorkBot`) ma'lumot oladi — SQLite faylga to'g'ridan-to'g'ri
   kirmaydi (Railway'da har bir xizmat alohida konteynerda, fayl almashish
   yo'q). HR'ning kodiga yoki bazasiga hech qanday yozuv qilinmaydi.
2. **`task_quantity_logs`** jadvalidan o'qiydi (`plan_tasks`/`task_quantities`
   emas — ular joriy holatning o'zgaruvchan yig'indisi, `task_quantity_logs`
   esa HR botining o'zi ishlatadigan O'ZGARMAS hisobot jurnali).
3. Har bir qatorning `operation_key`i (HR botining o'z idempotentlik
   kaliti) — bizning `source_id`imizning asosi.
4. Har bir hisobot matnini (`task_text`) Ombor katalogidagi (faqat
   `FINISHED`, faqat `external_code`i bor) mahsulotlar bilan solishtiradi
   (`erp_bridge_kit.best_name_match`).
5. HR har xil vazifada har xil birlikda hisobot berishi mumkin (masalan
   ba'zilari "box"da, ba'zilari to'g'ridan-to'g'ri "partiya"da — HR
   kodini o'qib aniqlandi: `unit` maydoni erkin, faqat "box"/"dona" kabi
   taniqli so'zlar normallashtiriladi, qolgani xom holda saqlanadi).
   `UNIT_MULTIPLIERS` (JSON, sozlanadigan) har bir birlik uchun 1 dona
   (banka)ga necha marta ko'paytirishni belgilaydi — standart:
   `box=24, partiya=300, dona=1, ta=1`. Xaritada yo'q birlik kelsa,
   xavfsizlik uchun konvertatsiya qilinmaydi, review'ga tushadi.
6. Ishonchli moslik topilsa → Ombor'ning `POST /production-batches`iga
   `source_id=hr-op:{operation_key}`, `completed_units=<dona soni>` bilan
   yuboradi (idempotent). Ombor tarafida bu dona darhol tayyor mahsulot
   qoldig'iga qo'shiladi; xomashyo esa faqat to'liq partiya (300)
   yig'ilganda kamayadi (Ombor'ning W4 hisoblagichi, batafsil:
   `abc2019/inventory/docs/erp_integration_plan.md`).
7. Moslik noaniq bo'lsa (yoki umuman topilmasa) → **hech qachon avtomatik
   yozilmaydi** — mahalliy holat bazasida `NEEDS_REVIEW` sifatida saqlanadi.
8. Ombor vaqtincha ishlamay qolsa → `FAILED`, keyingi tsiklda **avtomatik
   qayta uriniladi** (faqat `SYNCED` yozuvlar butunlay chetlab o'tiladi).

## ⚠️ Productionga chiqarishdan oldin tasdiqlash kerak

- ~~HR'ning "bajarilgan" belgisi~~ — **hal qilindi**: HR'ning haqiqiy
  kodini (`abc2019/ShohonaWorkBot/db.py`) o'qib tasdiqlandi — `status`
  qiymatlari `'pending'`/`'done'`/`'not_done'` (`'completed'` emas), va
  eng ishonchli manba sifatida `task_quantity_logs` (o'zgarmas jurnal)
  tanlandi.
- ~~`completed_qty`/birlik nisbati~~ — **hal qilindi (kengaytirilgan)**:
  1 box = 24 dona (tasdiqlangan), 1 partiya = 300 dona (Ombor'ning loyiha
  qoidasi). HR kodini chuqurroq o'qib, `unit` maydoni qattiq "box" emas,
  vazifaga qarab har xil (masalan ba'zi vazifalar to'g'ridan-to'g'ri
  "partiya" birligida hisobot beradi) ekanligi aniqlandi —
  `UNIT_MULTIPLIERS` shuni hisobga oladi. Ombor'ning W4'i dona-asoslangan
  hisoblagichga o'zgartirildi.
- ~~HR bazasiga qanday kirish~~ — **hal qilindi**: to'g'ridan-to'g'ri fayl
  o'rniga HR'ga qo'shilgan kichik, izolyatsiyalangan `internal_api.py`
  orqali (`abc2019/ShohonaWorkBot` PR — **hali merge qilinmagan, ko'rib
  chiqish kutilmoqda**).
- **Haqiqiy production HR ma'lumotlarida hali sinalmagan** — soxta (fake)
  va real HR sxemasiga mos test bazasi bilan (funksional, E2E) tekshirilgan,
  lekin haqiqiy Railway muhitida ikkalasi bir-biriga ulanib ishlashi hali
  tasdiqlanmagan.

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

26 test: HR reader (HTTP orqali, `mock transport` bilan tarmoqsiz —
auth header, xato holatlari), holat bazasi (SYNCED chetlab o'tiladi,
FAILED/NEEDS_REVIEW qayta uriniladi), orchestratsiya (moslik topilganda
push, noaniq bo'lganda review, xomashyo hech qachon tanlanmasligi, birlik→dona
konvertatsiyasi va sozlanadigan nisbat, noma'lum birlik review'ga tushishi,
Ombor xatosidan keyin qayta tiklanish, takroriy qayta ishlanmaslik, Ombor
sozlanmaganda xavfsiz to'xtash). Bundan tashqari, HR'ning haqiqiy
`internal_api.py`si bilan real HTTP orqali end-to-end tekshirilgan.

## Deploy (Railway)

Bu xizmat **HR botidan alohida** Railway xizmati sifatida deploy qilinadi
(fayl emas, tarmoq orqali gaplashadi):

1. `abc2019/ShohonaWorkBot`dagi PR (ichki API qo'shilgan) merge qilinishi
   va HR xizmatida `INTERNAL_API_TOKEN` o'zgaruvchisi sozlanishi kerak.
2. Bu repo'ni yangi Railway xizmati sifatida deploy qiling.
3. `HR_INTERNAL_API_BASE_URL` — Railway ichki tarmoq manzili (odatda
   `http://<hr-xizmat-nomi>.railway.internal:8089`), `HR_INTERNAL_API_TOKEN`
   — HR xizmatidagi bilan **bir xil** qiymat.
4. `OMBOR_API_BASE_URL`ni sozlang.
5. `STATE_DATABASE_PATH` uchun Railway Volume tavsiya etiladi — aks holda
   har qayta deployda holat yo'qolib, hodisalar qayta tekshiriladi
   (zararsiz, chunki Ombor tarafida ham idempotent, lekin ortiqcha ish).
