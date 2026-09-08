# production-sync

HR botining bajarilgan tasklarini (`plan_tasks` + `task_quantities`) Ombor
moduliga (`POST /production-batches`, W4 kontrakti) avtomatik yuboruvchi
kichik ko'prik xizmati.

To'liq kontekst: `abc2019/inventory` repo'sidagi
`docs/erp_integration_plan.md` (bo'lim 5).

## Qanday ishlaydi

1. HR botining SQLite bazasidan **faqat o'qish** rejimida (`mode=ro&immutable=1`)
   ulanadi — HR'ning kodiga yoki bazasiga hech qanday yozuv qilinmaydi.
2. `completed_qty > 0 AND submitted_at IS NOT NULL` bo'lgan (va bekor
   qilinmagan) tasklarni oladi.
3. Har bir task matnini (`task_text`) Ombor katalogidagi (faqat `FINISHED`,
   faqat `external_code`i bor) mahsulotlar bilan solishtiradi
   (`erp_bridge_kit.best_name_match`).
4. Ishonchli moslik topilsa → Ombor'ning `POST /production-batches`iga
   `source_id=hr-task:{task_id}` bilan yuboradi (idempotent).
5. Moslik noaniq bo'lsa (yoki umuman topilmasa) → **hech qachon avtomatik
   yozilmaydi** — mahalliy holat bazasida `NEEDS_REVIEW` sifatida saqlanadi.
6. Ombor vaqtincha ishlamay qolsa → `FAILED`, keyingi tsiklda **avtomatik
   qayta uriniladi** (faqat `SYNCED` tasklar butunlay chetlab o'tiladi).

## ⚠️ Productionga chiqarishdan oldin tasdiqlash kerak

- **HR'ning "bajarilgan" belgisi.** Bu xizmat `task_quantities.submitted_at
  IS NOT NULL AND completed_qty > 0`ni "bajarilgan" belgisi sifatida
  ishlatadi (`plan_tasks.status`ning aniq matn qiymatlari — masalan
  "completed"/"bajarildi" — loyihaning bu bosqichida tasdiqlanmagan edi).
  HR jamoasi bilan tekshiring; kerak bo'lsa `app/hr_reader.py`dagi
  so'rovni moslashtiring.
- **`completed_qty`ning ma'nosi.** Hozir bu son to'g'ridan-to'g'ri
  Ombor'ning `batch_count`iga (bajarilgan PARTIYA soni, 1 partiya=300)
  sifatida yuboriladi. Agar HR'da bu son aslida DONA sonini bildirsa
  (partiya emas), `app/sync.py`da `batch_count=task.completed_qty // 300`
  kabi konvertatsiya qo'shish kerak bo'ladi.
- **Haqiqiy HR bazasiga ulanib sinalmagan** — faqat soxta (fake) schema
  bilan testlangan (`tests/conftest.py`). Real muhitda birinchi marta
  ishga tushirishdan oldin, kichik `HR_DATABASE_PATH`ning **nusxasi**
  (production emas) bilan tekshirib ko'rish tavsiya etiladi.

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
