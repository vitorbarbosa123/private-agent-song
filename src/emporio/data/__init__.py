"""Pipeline de tratamento dos dados brutos fornecidos pela loja.

Princípio geral: **sinalizar em vez de corrigir silenciosamente**. Só alteramos um
valor quando a correção é inequívoca (ex.: erro de digitação). Nos demais casos
mantemos o dado original, adicionamos colunas derivadas/flags e registramos o
problema no relatório de qualidade (`data/processed/data_quality_report.md`).
"""
