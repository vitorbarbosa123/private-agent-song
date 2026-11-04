"""Tratamento do catálogo de produtos.

Inconsistências tratadas:
- erro de digitação no nome (correção explícita e auditável em `NAME_CORRECTIONS`);
- `specs` em JSON com esquemas diferentes por categoria e com o campo `strings`
  significando ora o tipo de corda ('nylon'/'steel'), ora a quantidade ('4', '6');
- descrições que contradizem o nome ou as especificações (marca/modelo de outro
  fabricante, número de cordas/teclas diferente);
- combinações incoerentes de status e estoque (descontinuado com estoque, esgotado
  ativo, pré-lançamento com estoque).
"""

from __future__ import annotations

import json
import re

import pandas as pd

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import (
    clean_text,
    drop_duplicate_ids,
    drop_null,
    normalize_for_search,
    parse_date,
    parse_float,
    parse_int,
)

TABLE = "products"

VALID_STATUSES = {"active", "discontinued", "coming_soon"}

# product_id -> (nome original esperado, nome corrigido). Só corrige se o original bater.
NAME_CORRECTIONS: dict[int, tuple[str, str]] = {
    84: ("Giannini GN-15 Nylon Cedr Natural", "Giannini GN-15 Nylon Cedro Natural"),
}

# Marcas conhecidas (forma normalizada -> forma de exibição).
BRANDS: dict[str, str] = {
    "crafter": "Crafter", "fender": "Fender", "giannini": "Giannini", "gibson": "Gibson",
    "ibanez": "Ibanez", "kala": "Kala", "kalani": "Kalani", "korg": "Korg", "martin": "Martin",
    "music man": "Music Man", "nord": "Nord", "ohana": "Ohana", "pearl": "Pearl", "prs": "PRS",
    "roland": "Roland", "rozini": "Rozini", "shelby": "Shelby", "tagima": "Tagima",
    "takamine": "Takamine", "tama": "Tama", "taylor": "Taylor", "yamaha": "Yamaha",
}
# Modelos/tecnologias que identificam um fabricante mesmo sem o nome da marca.
MODEL_HINTS: dict[str, str] = {
    "jazz bass": "fender", "precision": "fender", "stratocaster": "fender",
    "telecaster": "fender", "stingray": "music man", "les paul": "gibson",
    "stage custom": "yamaha", "export": "pearl", "star-mount": "tama",
    "supernatural": "roland", "nord stage": "nord",
}

SPEC_LABELS: dict[str, str] = {
    "top": "tampo", "back_sides": "fundo e laterais", "neck": "braço", "body": "corpo",
    "string_type": "cordas", "string_count": "número de cordas", "scale": "escala",
    "electronics": "eletrônica/captação", "color": "cor", "shells": "cascos",
    "pieces": "peças", "hardware_included": "ferragens inclusas", "keys": "teclas",
    "type": "tipo", "polyphony": "polifonia",
}
_INT_SPECS = {"keys", "polyphony", "pieces"}
_STRING_TYPES = {"nylon": "nylon", "steel": "aço"}


def _word_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])")


_BRAND_PATTERNS = {b: _word_pattern(b) for b in BRANDS}
_HINT_PATTERNS = {h: _word_pattern(h) for h in MODEL_HINTS}


def brands_in(text: object) -> set[str]:
    """Marcas citadas no texto, diretamente ou por um modelo característico."""
    normalized = normalize_for_search(text)
    found = {b for b, p in _BRAND_PATTERNS.items() if p.search(normalized)}
    found |= {MODEL_HINTS[h] for h, p in _HINT_PATTERNS.items() if p.search(normalized)}
    return found


def normalize_specs(raw: object, *, log: IssueLog, record_id: object) -> dict[str, object]:
    text = clean_text(raw)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.add(TABLE, record_id, "invalid_specs_json", Severity.ERROR,
                f"'specs' não é um JSON válido: {text[:80]!r}.", "Especificações descartadas.")
        return {}
    if not isinstance(data, dict):
        log.add(TABLE, record_id, "invalid_specs_json", Severity.ERROR,
                "'specs' não é um objeto JSON.", "Especificações descartadas.")
        return {}

    specs: dict[str, object] = {}
    for key, value in data.items():
        k = (clean_text(key) or "").lower()
        v = clean_text(value) if isinstance(value, str) else value
        if k == "strings":
            if isinstance(v, str) and v.isdigit():
                specs["string_count"] = int(v)
            elif isinstance(v, str) and v.lower() in _STRING_TYPES:
                specs["string_type"] = _STRING_TYPES[v.lower()]
            else:
                specs["strings"] = v
        elif k in _INT_SPECS and isinstance(v, str) and v.isdigit():
            specs[k] = int(v)
        elif k == "electronics" and isinstance(v, str) and v.lower() in {"yes", "no"}:
            specs[k] = v.lower() == "yes"
        elif k == "hardware" and isinstance(v, str):
            specs["hardware_included"] = v.lower() == "included"
        else:
            specs[k] = v
    return specs


def find_description_conflicts(name: str, description: str | None, specs: dict[str, object]) -> list[str]:
    """Motivos pelos quais a descrição contradiz o nome ou as especificações."""
    if not description:
        return []
    reasons: list[str] = []
    name_brands = brands_in(name)
    foreign = brands_in(description) - name_brands
    if name_brands and foreign:
        reasons.append(
            f"descrição cita {', '.join(sorted(BRANDS[b] for b in foreign))}, "
            f"mas o produto é {', '.join(sorted(BRANDS[b] for b in name_brands))}"
        )
    desc = normalize_for_search(description)
    for pattern, spec_key, label in (
        (r"(\d+)\s+cordas", "string_count", "cordas"),
        (r"(\d+)\s+teclas", "keys", "teclas"),
    ):
        match = re.search(pattern, desc)
        if match and spec_key in specs and int(match.group(1)) != specs[spec_key]:
            reasons.append(f"descrição cita {match.group(1)} {label}, specs indicam {specs[spec_key]}")
    return reasons


def _format_spec_value(value: object) -> str:
    if value is True:
        return "sim"
    if value is False:
        return "não"
    return str(value)


def build_specs_description(specs: dict[str, object]) -> str:
    parts = [f"{SPEC_LABELS.get(k, k)}: {_format_spec_value(v)}" for k, v in specs.items()]
    return "Especificações cadastradas — " + "; ".join(parts) + "." if parts else ""


def classify_availability(status: str | None, stock: int) -> str:
    if status == "discontinued":
        return "discontinued"
    if status == "coming_soon":
        return "coming_soon"
    if status == "active":
        return "in_stock" if stock > 0 else "out_of_stock"
    return "unknown"


def clean_products(raw: pd.DataFrame, categories: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    df = raw.copy()
    df["product_id"] = [
        parse_int(v, log=log, table=TABLE, record_id=v, field="product_id") for v in df["product_id"]
    ]
    df = drop_null(df, "product_id", log=log, table=TABLE, id_col="product_id")
    df["product_id"] = df["product_id"].astype(int)
    df = drop_duplicate_ids(df, "product_id", log=log, table=TABLE)

    records: list[dict[str, object]] = []
    valid_categories = set(categories["category_id"])
    strings_semantics_seen: set[str] = set()

    for row in df.to_dict("records"):
        pid = row["product_id"]
        kw = {"log": log, "table": TABLE, "record_id": pid}
        sellable_blockers: list[str] = []

        name = clean_text(row["name"]) or ""
        if pid in NAME_CORRECTIONS and name == NAME_CORRECTIONS[pid][0]:
            name = NAME_CORRECTIONS[pid][1]
            log.add(TABLE, pid, "name_typo", Severity.INFO,
                    f"Erro de digitação no nome: '{NAME_CORRECTIONS[pid][0]}'.",
                    f"Nome corrigido para '{name}'.")
        if not name:
            log.add(TABLE, pid, "missing_name", Severity.ERROR, "Produto sem nome.",
                    "Marcado como não vendável.")
            sellable_blockers.append("sem nome")

        category_id = parse_int(row["category_id"], field="category_id", **kw)
        if category_id not in valid_categories:
            log.add(TABLE, pid, "unknown_category", Severity.ERROR,
                    f"category_id {row['category_id']!r} não existe na tabela de categorias.",
                    "Marcado como não vendável.")
            sellable_blockers.append("categoria inválida")

        price = parse_float(row["price_brl"], field="price_brl", **kw)
        if price is None or price <= 0:
            log.add(TABLE, pid, "invalid_price", Severity.ERROR,
                    f"Preço inválido: {row['price_brl']!r}.", "Marcado como não vendável.")
            price = None
            sellable_blockers.append("preço inválido")

        stock = parse_int(row["stock_quantity"], field="stock_quantity", **kw)
        if stock is None or stock < 0:
            log.add(TABLE, pid, "invalid_stock", Severity.ERROR,
                    f"Estoque inválido: {row['stock_quantity']!r}.", "Estoque considerado 0.")
            stock = 0

        status = normalize_for_search(row["status"]) or None
        if status not in VALID_STATUSES:
            log.add(TABLE, pid, "invalid_status", Severity.ERROR,
                    f"Status desconhecido: {row['status']!r}.", "Marcado como não vendável.")
            status = None

        specs = normalize_specs(row["specs"], log=log, record_id=pid)
        if "string_count" in specs:
            strings_semantics_seen.add("count")
        if "string_type" in specs:
            strings_semantics_seen.add("type")

        description_original = clean_text(row["description"])
        conflicts = find_description_conflicts(name, description_original, specs)
        if conflicts:
            log.add(TABLE, pid, "description_conflict", Severity.WARNING,
                    f"'{name}': " + "; ".join(conflicts) + ".",
                    "Descrição original preservada em 'description_original'; 'description' "
                    "substituída por texto gerado a partir de nome + specs; "
                    "description_verified=False.")
            description = build_specs_description(specs)
        else:
            description = description_original

        availability = classify_availability(status, stock)
        if availability == "discontinued" and stock > 0:
            log.add(TABLE, pid, "discontinued_with_stock", Severity.WARNING,
                    f"'{name}' está descontinuado mas tem {stock} unidade(s) em estoque.",
                    "Tratado como indisponível (seção 7.3: produto descontinuado). Estoque "
                    "residual a confirmar com a equipe.")
        elif availability == "coming_soon" and stock > 0:
            log.add(TABLE, pid, "coming_soon_with_stock", Severity.WARNING,
                    f"'{name}' está como 'coming_soon' mas tem {stock} unidade(s) em estoque.",
                    "Tratado como indisponível para venda até a mudança de status.")
        elif availability == "out_of_stock":
            log.add(TABLE, pid, "out_of_stock", Severity.INFO,
                    f"'{name}' está ativo, porém esgotado.",
                    "is_sellable=False; o agente deve sugerir alternativas (seção 7.3).")

        name_brands = brands_in(name)
        records.append({
            "product_id": pid,
            "name": name,
            "brand": ", ".join(sorted(BRANDS[b] for b in name_brands)) or None,
            "category_id": category_id,
            "price_brl": price,
            "stock_quantity": stock,
            "status": status,
            "availability": availability,
            "is_sellable": availability == "in_stock" and not sellable_blockers,
            "description": description,
            "description_original": description_original,
            "description_verified": not conflicts,
            "specs": specs,
            "created_at": parse_date(row["created_at"], field="created_at", **kw),
            "name_search": normalize_for_search(name),
        })

    if strings_semantics_seen == {"count", "type"}:
        log.add(TABLE, None, "ambiguous_specs_strings", Severity.INFO,
                "O campo specs.strings indica o tipo de corda nos violões/ukuleles ('nylon', "
                "'steel') e a quantidade de cordas nas guitarras/baixos ('4', '6').",
                "Separado em specs.string_type ('nylon'/'aço') e specs.string_count (inteiro).")

    products = pd.DataFrame.from_records(records)
    _flag_duplicate_names(products, log)
    return products.sort_values("product_id").reset_index(drop=True)


def _flag_duplicate_names(products: pd.DataFrame, log: IssueLog) -> None:
    dupes = products[products["name_search"].duplicated(keep=False)]
    for _, group in dupes.groupby("name_search"):
        ids = ", ".join(str(i) for i in group["product_id"])
        log.add(TABLE, ids, "duplicate_name", Severity.WARNING,
                f"Produtos com o mesmo nome: '{group['name'].iloc[0]}'.",
                "Mantidos; buscas por nome devem retornar todos.")
