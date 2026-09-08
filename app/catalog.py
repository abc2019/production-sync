def build_candidates(products: list[dict]) -> dict[str, str]:
    """
    {external_code: name} — faqat external_code'i borlar (kodsiz mahsulotga
    moslashtirib bo'lmaydi, chunki Ombor'ning production-batches kontrakti
    finished_product_id talab qiladi, biz esa faqat kod orqali topamiz).
    """
    return {
        p["external_code"]: p["name"]
        for p in products
        if p.get("external_code") and p.get("warehouse_type") == "FINISHED"
    }


def index_by_code(products: list[dict]) -> dict[str, dict]:
    return {p["external_code"]: p for p in products if p.get("external_code")}
