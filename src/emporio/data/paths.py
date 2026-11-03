"""Localização dos arquivos de entrada e saída do pipeline."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = RAW_DIR / "processed"

# Nomes originais dos arquivos, como entregues pela loja.
RAW_CSV_FILES: dict[str, str] = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
}
POLICIES_PDF_NAME = "políticas_da_loja.pdf"
