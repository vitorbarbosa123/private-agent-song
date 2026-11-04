"""Orquestra o tratamento de todos os dados e grava os artefatos processados.

Uso:
    uv run emporio-clean-data            # lê data/, grava em data/processed/
    uv run emporio-clean-data --raw-dir X --out-dir Y

Saídas (em data/processed/):
    *.csv                    tabelas tratadas (specs em JSON)
    emporio.db               as mesmas tabelas em SQLite, para consultas do agente
    policies.md              manual em Markdown, dividido por seção
    policy_sections.json     seções do manual (insumo para RAG)
    store_facts.json         dados institucionais canônicos + conflitos resolvidos
    data_quality_issues.csv  todos os problemas encontrados
    data_quality_report.md   relatório legível dos problemas e das decisões
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from emporio import policy_rules
from emporio.data.categories import clean_categories, flag_empty_categories
from emporio.data.customers import clean_customers
from emporio.data.issues import IssueLog, Severity
from emporio.data.orders import clean_order_items, clean_orders
from emporio.data.paths import POLICIES_PDF_NAME, PROCESSED_DIR, RAW_CSV_FILES, RAW_DIR
from emporio.data.policies import process_policies
from emporio.data.products import clean_products
from emporio.data.promotions import apply_pricing, clean_promotions


@dataclass
class CleanData:
    tables: dict[str, pd.DataFrame]
    policy_sections: list[dict[str, str | None]]
    policies_markdown: str
    log: IssueLog = field(default_factory=IssueLog)


def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Lê os CSVs como texto puro: o parsing de tipos é feito (e auditado) pelo pipeline."""
    return {
        name: pd.read_csv(raw_dir / filename, dtype=str, keep_default_na=False, encoding="utf-8")
        for name, filename in RAW_CSV_FILES.items()
    }


def run_pipeline(raw_dir: Path = RAW_DIR) -> CleanData:
    log = IssueLog()
    raw = load_raw_tables(raw_dir)

    categories = clean_categories(raw["categories"], log)
    products = clean_products(raw["products"], categories, log)
    promotions = clean_promotions(raw["promotions"], products, log)
    products = apply_pricing(products, promotions, log)
    categories = flag_empty_categories(categories, products, log)
    customers = clean_customers(raw["customers"], log)
    items = clean_order_items(raw["order_items"], products, log)
    orders, items = clean_orders(raw["orders"], items, customers, products, log)
    sections, markdown = process_policies(raw_dir / POLICIES_PDF_NAME, log)

    tables = {
        "categories": categories,
        "products": products,
        "promotions": promotions,
        "customers": customers,
        "orders": orders,
        "order_items": items,
    }
    return CleanData(tables, sections, markdown, log)


# --- Escrita dos artefatos ---------------------------------------------------


def _serializable(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].map(lambda v: isinstance(v, dict)).any():
            out[col] = out[col].map(lambda v: json.dumps(v, ensure_ascii=False))
        elif out[col].map(lambda v: isinstance(v, date)).any():
            out[col] = out[col].map(lambda v: v.isoformat() if isinstance(v, date) else None)
    return out


def write_outputs(data: CleanData, out_dir: Path = PROCESSED_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    db_path = out_dir / "emporio.db"
    db_path.unlink(missing_ok=True)
    with sqlite3.connect(db_path) as conn:
        for name, df in data.tables.items():
            flat = _serializable(df)
            flat.to_csv(out_dir / f"{name}.csv", index=False)
            flat.to_sql(name, conn, index=False)

    (out_dir / "policies.md").write_text(data.policies_markdown, encoding="utf-8")
    _write_json(out_dir / "policy_sections.json", data.policy_sections)
    _write_json(out_dir / "store_facts.json", {
        "store": policy_rules.STORE_INFO,
        "policy_resolutions": policy_rules.resolutions_as_dicts(),
    })
    data.log.to_frame().to_csv(out_dir / "data_quality_issues.csv", index=False)
    (out_dir / "data_quality_report.md").write_text(render_report(data), encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _md_cell(value: object) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).replace("|", "\\|")


def render_report(data: CleanData) -> str:
    issues = data.log.to_frame()
    lines = [
        "# Relatório de qualidade dos dados",
        "",
        "Gerado automaticamente por `uv run emporio-clean-data`. Não edite à mão.",
        "",
        "Princípio adotado: **sinalizar em vez de corrigir silenciosamente**. Valores só são "
        "alterados quando a correção é inequívoca; nos demais casos o dado original é mantido "
        "e o problema fica exposto em colunas derivadas e neste relatório.",
        "",
        "## Resumo",
        "",
        "| Tabela | Registros tratados | info | warning | error |",
        "|---|---:|---:|---:|---:|",
    ]
    counts = issues.groupby(["table", "severity"]).size().unstack(fill_value=0) if len(issues) else pd.DataFrame()
    for table in [*data.tables, "policies"]:
        n = len(data.tables[table]) if table in data.tables else len(data.policy_sections)
        row = counts.loc[table] if table in counts.index else {}
        cells = [str(int(row.get(s, 0))) for s in Severity]
        label = f"{table} (seções)" if table == "policies" else table
        lines.append(f"| {label} | {n} | " + " | ".join(cells) + " |")

    lines += ["", "## Problemas por regra", ""]
    for (table, rule), group in issues.groupby(["table", "rule"], sort=False):
        severity = group["severity"].iloc[0]
        lines += [f"### `{table}` · `{rule}` ({severity}, {len(group)})", "",
                  "| Registro | Problema | Ação |", "|---|---|---|"]
        for issue in group.itertuples():
            lines.append(f"| {_md_cell(issue.record_id)} | {_md_cell(issue.message)} | {_md_cell(issue.action)} |")
        lines.append("")

    lines += ["## Interpretações adotadas para o manual de políticas", ""]
    for r in policy_rules.RESOLUTIONS:
        lines += [f"- **{r.topic}** (seção {r.sections}): {r.decision} _Motivo:_ {r.rationale}"]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trata os dados brutos da Empório da Música.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args(argv)

    data = run_pipeline(args.raw_dir)
    write_outputs(data, args.out_dir)

    issues = data.log.to_frame()
    by_severity = issues["severity"].value_counts().to_dict() if len(issues) else {}
    print(f"Tabelas gravadas em {args.out_dir}")
    for name, df in data.tables.items():
        print(f"  {name:<12} {len(df):>4} registros")
    print(f"  policies     {len(data.policy_sections):>4} seções")
    print("Problemas encontrados: " + ", ".join(f"{k}={v}" for k, v in sorted(by_severity.items())))
    print(f"Relatório: {args.out_dir / 'data_quality_report.md'}")


if __name__ == "__main__":
    main()
