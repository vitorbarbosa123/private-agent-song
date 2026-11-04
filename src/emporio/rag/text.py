"""Pré-processamento de texto em português para a busca lexical (BM25)."""

from __future__ import annotations

import re
from functools import lru_cache

import snowballstemmer

from emporio.data.utils import normalize_for_search

_TOKEN = re.compile(r"[a-z0-9]+")
# Plurais -ões/-ães: sem acento, "devolucoes" e "devolucao" teriam radicais diferentes.
_PLURAL_AO = re.compile(r"(?<=\w{2})[oa]es$")

# Stopwords comuns do português (já sem acentos, pois o texto é normalizado antes).
STOPWORDS = frozenset("""
a ao aos as ate com como da das de dela dele do dos e ela ele em entre era essa esse esta
este eu foi ha isso isto ja la lhe mais mas me mesmo meu minha muito na nas nem no nos nossa
nosso num numa o os ou para pela pelo per por qual quando que quem se sem ser seu sua so
tambem te tem tenho ter um uma umas uns voce voces vou vai sao estou esta estao pra pro
posso pode podem gostaria quero queria
""".split())

# Expansões de consulta: o cliente fala "devolver", o manual fala "devolução"/"arrependimento".
# Só a consulta é expandida; o índice fica fiel ao texto do manual.
QUERY_EXPANSIONS: dict[str, str] = {
    "devolver": "devolucao arrependimento reembolso",
    "devolvo": "devolucao arrependimento reembolso",
    "arrependi": "arrependimento devolucao",
    "desistir": "arrependimento devolucao",
    "trocar": "troca",
    "quebrou": "defeito garantia",
    "quebrado": "defeito garantia",
    "estragou": "defeito garantia",
    "parcelar": "parcelamento parcela credito",
    "vezes": "parcelamento parcela",
    "pagar": "pagamento",
    "entregam": "entrega frete",
    "envio": "entrega frete",
    "chega": "entrega prazo",
    "rastrear": "rastreamento codigo",
    "rastreio": "rastreamento codigo",
    "abre": "horario funcionamento",
    "abrem": "horario funcionamento",
    "aberto": "horario funcionamento",
    "aberta": "horario funcionamento",
    "fecha": "horario funcionamento",
    "funciona": "horario funcionamento",
    "endereco": "endereco localizacao dados empresa",
    "telefone": "telefone whatsapp contato",
    "zap": "whatsapp",
    "dados": "dados privacidade lgpd",
    "reclamar": "reclamacao",
    "reclamacao": "reclamacao",
    "amassado": "avaria transporte recusar recebimento",
    "avariado": "avaria transporte recusar recebimento",
    "acessorio": "acessorios instrumentos",
    "acessorios": "acessorios instrumentos",
    "apagar": "exclusao dados privacidade",
    "apaguem": "exclusao dados privacidade",
    "excluir": "exclusao dados privacidade",
    "deletar": "exclusao dados privacidade",
    "cadastro": "dados privacidade",
}

# Expressões de várias palavras ("mandar de volta" = devolver).
PHRASE_EXPANSIONS: dict[str, str] = {
    "de volta": "devolucao arrependimento",
    "nao gostar": "arrependimento devolucao",
    "nao gostei": "arrependimento devolucao",
    "loja fisica": "endereco horario funcionamento",
}


@lru_cache(maxsize=1)
def _stemmer() -> snowballstemmer.stemmer:
    return snowballstemmer.stemmer("portuguese")


def tokenize(text: str) -> list[str]:
    """Normaliza (minúsculas, sem acentos), remove stopwords e reduz ao radical."""
    words = [_PLURAL_AO.sub("ao", w) for w in _TOKEN.findall(normalize_for_search(text)) if w not in STOPWORDS]
    return _stemmer().stemWords(words)


def tokenize_query(query: str) -> list[str]:
    normalized = normalize_for_search(query)
    expansions = [QUERY_EXPANSIONS[w] for w in _TOKEN.findall(normalized) if w in QUERY_EXPANSIONS]
    expansions += [exp for phrase, exp in PHRASE_EXPANSIONS.items() if phrase in normalized]
    return tokenize(" ".join([normalized, *expansions]))
