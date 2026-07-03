"""
services/cnpj_service.py

Serviço responsável por consultar dados cadastrais de empresas pelo CNPJ.

Fluxo atual:
1. Valida o documento informado.
2. Consulta cache local em storage/cache/cnpj_cache.json.
3. Se não existir cache, consulta CNPJ.ws como fonte principal.
4. Se CNPJ.ws falhar, tenta BrasilAPI como fallback.
5. Se alguma API funcionar, salva no cache local.
6. Se houver limite de requisições, retorna mensagem amigável:
   "Aguarde 1 minuto e tente novamente"

Uso previsto:
- Tela de Clientes
- Campo CPF/CNPJ
- Botão/lupa para buscar dados automaticamente
- Preenchimento automático de:
    nome/razão social
    telefone
    WhatsApp
    e-mail
    endereço

Observação:
- CPF não deve ser consultado por API pública.
- Para CPF, manter cadastro manual por segurança e LGPD.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests


CNPJ_WS_URL = "https://publica.cnpj.ws/cnpj/{cnpj}"
BRASILAPI_CNPJ_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"

DEFAULT_TIMEOUT = 10
DEBUG_CNPJ_SERVICE = True

CACHE_DIR = Path("storage/cache")
CACHE_FILE = CACHE_DIR / "cnpj_cache.json"

RATE_LIMIT_USER_MESSAGE = "Aguarde 1 minuto e tente novamente"


def debug_print(message: str) -> None:
    """
    Print centralizado para acompanhar o processo no terminal.

    Para desligar os prints, altere:
    DEBUG_CNPJ_SERVICE = False
    """
    if DEBUG_CNPJ_SERVICE:
        print(f"[CNPJ_SERVICE] {message}", flush=True)


def debug_error(message: str) -> None:
    """
    Print centralizado para erros no terminal.
    """
    if DEBUG_CNPJ_SERVICE:
        print(f"[CNPJ_SERVICE][ERRO] {message}", flush=True)
        print("[CNPJ_SERVICE] Processo interrompido", flush=True)


class CNPJConsultaError(Exception):
    """Erro controlado para falhas na consulta de CNPJ."""

    pass


@dataclass
class ClienteCNPJDTO:
    """Objeto padronizado para alimentar o formulário de cliente."""

    nome: str = ""
    razao_social: str = ""
    nome_fantasia: str = ""
    cpf_cnpj: str = ""
    cnpj_limpo: str = ""
    telefone: str = ""
    whatsapp: str = ""
    email: str = ""
    endereco: str = ""
    cep: str = ""
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    situacao: str = ""
    cnae: str = ""
    fonte: str = ""

    def to_form_dict(self) -> Dict[str, str]:
        """
        Retorna os campos no formato mais simples para uso no st.session_state.
        """
        return {
            "nome": self.nome,
            "cpf_cnpj": self.cpf_cnpj,
            "telefone": self.telefone,
            "whatsapp": self.whatsapp,
            "email": self.email,
            "endereco": self.endereco,
        }

    def to_dict(self) -> Dict[str, str]:
        """
        Retorna todos os campos disponíveis.
        Útil futuramente para banco de dados ou auditoria.
        """
        return {
            "nome": self.nome,
            "razao_social": self.razao_social,
            "nome_fantasia": self.nome_fantasia,
            "cpf_cnpj": self.cpf_cnpj,
            "cnpj_limpo": self.cnpj_limpo,
            "telefone": self.telefone,
            "whatsapp": self.whatsapp,
            "email": self.email,
            "endereco": self.endereco,
            "cep": self.cep,
            "logradouro": self.logradouro,
            "numero": self.numero,
            "complemento": self.complemento,
            "bairro": self.bairro,
            "municipio": self.municipio,
            "uf": self.uf,
            "situacao": self.situacao,
            "cnae": self.cnae,
            "fonte": self.fonte,
        }


def limpar_documento(valor: Optional[str]) -> str:
    """
    Remove tudo que não for número.
    """
    documento_limpo = re.sub(r"\D", "", valor or "")
    debug_print(f"Documento recebido: {valor}")
    debug_print(f"Documento limpo: {documento_limpo}")
    return documento_limpo


def eh_cnpj(valor: Optional[str]) -> bool:
    """
    Verifica se o documento informado possui tamanho de CNPJ.
    """
    return len(limpar_documento(valor)) == 14


def eh_cpf(valor: Optional[str]) -> bool:
    """
    Verifica se o documento informado possui tamanho de CPF.
    """
    return len(limpar_documento(valor)) == 11


def texto_limpo(valor: Any) -> str:
    """
    Normaliza campos textuais vindos das APIs.
    """
    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.lower() in {"none", "null", "nan"}:
        return ""

    return texto


def get_nested(data: Dict[str, Any], *keys: str) -> Any:
    """
    Busca segura em dicionários aninhados.
    """
    atual: Any = data

    for key in keys:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(key)

    return atual


def formatar_cnpj(cnpj: Optional[str]) -> str:
    """
    Formata CNPJ no padrão 00.000.000/0000-00.
    """
    cnpj_limpo = re.sub(r"\D", "", cnpj or "")

    if len(cnpj_limpo) != 14:
        debug_print("CNPJ não formatado: tamanho diferente de 14 dígitos")
        return cnpj or ""

    cnpj_formatado = (
        f"{cnpj_limpo[0:2]}."
        f"{cnpj_limpo[2:5]}."
        f"{cnpj_limpo[5:8]}/"
        f"{cnpj_limpo[8:12]}-"
        f"{cnpj_limpo[12:14]}"
    )

    debug_print(f"CNPJ formatado: {cnpj_formatado}")
    return cnpj_formatado


def formatar_cep(cep: Optional[str]) -> str:
    """
    Formata CEP no padrão 00000-000.
    """
    cep_limpo = re.sub(r"\D", "", cep or "")

    if len(cep_limpo) != 8:
        return cep or ""

    return f"{cep_limpo[:5]}-{cep_limpo[5:]}"


def formatar_telefone(valor: Optional[str]) -> str:
    """
    Tenta formatar telefone brasileiro.

    Aceita retornos como:
    - 6133334444
    - 61999999999
    - (61) 99999-9999
    """
    numero = re.sub(r"\D", "", valor or "")

    if not numero:
        debug_print("Telefone vazio no retorno da API")
        return ""

    if len(numero) == 10:
        telefone_formatado = f"({numero[:2]}) {numero[2:6]}-{numero[6:]}"
        debug_print(f"Telefone formatado: {telefone_formatado}")
        return telefone_formatado

    if len(numero) == 11:
        telefone_formatado = f"({numero[:2]}) {numero[2:7]}-{numero[7:]}"
        debug_print(f"Telefone formatado: {telefone_formatado}")
        return telefone_formatado

    debug_print(f"Telefone retornado sem formatação padrão: {valor}")
    return valor or ""


def juntar_ddd_telefone(ddd: Any, telefone: Any) -> str:
    """
    Junta DDD + telefone retornados pela CNPJ.ws.
    """
    ddd_limpo = re.sub(r"\D", "", texto_limpo(ddd))
    telefone_limpo = re.sub(r"\D", "", texto_limpo(telefone))

    if not telefone_limpo:
        return ""

    return formatar_telefone(f"{ddd_limpo}{telefone_limpo}")


def validar_cnpj_basico(cnpj: Optional[str]) -> str:
    """
    Validação básica de CNPJ.

    Aqui validamos:
    - tamanho
    - se não é sequência repetida
    """
    debug_print("Validando CNPJ...")

    cnpj_limpo = limpar_documento(cnpj)

    if len(cnpj_limpo) != 14:
        debug_error("CNPJ inválido. Tamanho diferente de 14 números.")
        raise CNPJConsultaError("CNPJ inválido. Informe um CNPJ com 14 números.")

    if cnpj_limpo == cnpj_limpo[0] * 14:
        debug_error("CNPJ inválido. Sequência numérica repetida.")
        raise CNPJConsultaError("CNPJ inválido. Sequência numérica repetida.")

    debug_print("CNPJ OK")
    return cnpj_limpo


def montar_endereco_padrao(
    logradouro: str = "",
    numero: str = "",
    complemento: str = "",
    bairro: str = "",
    municipio: str = "",
    uf: str = "",
    cep: str = "",
) -> str:
    """
    Monta endereço padronizado.
    """
    debug_print("Montando endereço...")

    linha_1 = " ".join([p for p in [logradouro, numero] if p])
    linha_2 = " - ".join([p for p in [bairro, municipio, uf] if p])

    partes = [linha_1]

    if complemento:
        partes.append(complemento)

    if linha_2:
        partes.append(linha_2)

    if cep:
        partes.append(f"CEP {cep}")

    endereco = " | ".join([p for p in partes if p])

    if endereco:
        debug_print("Endereço OK")
        debug_print(f"Endereço montado: {endereco}")
    else:
        debug_print("Endereço vazio no retorno da API")

    return endereco


def carregar_cache() -> Dict[str, Any]:
    """
    Carrega o cache local de CNPJ.
    """
    debug_print("Verificando cache local...")

    try:
        if not CACHE_FILE.exists():
            debug_print("Arquivo de cache ainda não existe")
            return {}

        with CACHE_FILE.open("r", encoding="utf-8") as file:
            cache = json.load(file)

        if not isinstance(cache, dict):
            debug_print("Cache local inválido. Um novo cache será usado.")
            return {}

        debug_print("Cache local carregado com sucesso")
        return cache

    except Exception as exc:
        debug_error(f"Erro ao carregar cache local: {exc}")
        return {}


def salvar_cache(cache: Dict[str, Any]) -> None:
    """
    Salva o cache local de CNPJ.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        with CACHE_FILE.open("w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False, indent=2)

        debug_print(f"Cache salvo em: {CACHE_FILE}")

    except Exception as exc:
        debug_error(f"Erro ao salvar cache local: {exc}")


def buscar_no_cache(cnpj_limpo: str) -> Optional[ClienteCNPJDTO]:
    """
    Busca CNPJ no cache local.
    """
    cache = carregar_cache()
    item = cache.get(cnpj_limpo)

    if not item:
        debug_print("CNPJ não encontrado no cache")
        return None

    debug_print("CNPJ encontrado no cache")
    debug_print("Retornando dados do cache sem chamar API externa")

    dados = item.get("dados", item)

    return ClienteCNPJDTO(
        nome=dados.get("nome", ""),
        razao_social=dados.get("razao_social", ""),
        nome_fantasia=dados.get("nome_fantasia", ""),
        cpf_cnpj=dados.get("cpf_cnpj", formatar_cnpj(cnpj_limpo)),
        cnpj_limpo=dados.get("cnpj_limpo", cnpj_limpo),
        telefone=dados.get("telefone", ""),
        whatsapp=dados.get("whatsapp", dados.get("telefone", "")),
        email=dados.get("email", ""),
        endereco=dados.get("endereco", ""),
        cep=dados.get("cep", ""),
        logradouro=dados.get("logradouro", ""),
        numero=dados.get("numero", ""),
        complemento=dados.get("complemento", ""),
        bairro=dados.get("bairro", ""),
        municipio=dados.get("municipio", ""),
        uf=dados.get("uf", ""),
        situacao=dados.get("situacao", ""),
        cnae=dados.get("cnae", ""),
        fonte=dados.get("fonte", "Cache local"),
    )


def salvar_cnpj_no_cache(cnpj_limpo: str, dto: ClienteCNPJDTO) -> None:
    """
    Salva retorno normalizado no cache local.
    """
    debug_print("Salvando CNPJ no cache local...")

    cache = carregar_cache()

    cache[cnpj_limpo] = {
        "consultado_em": datetime.now().isoformat(timespec="seconds"),
        "fonte_original": dto.fonte,
        "dados": dto.to_dict(),
    }

    salvar_cache(cache)
    debug_print("CNPJ salvo no cache com sucesso")


def montar_dto_cnpj_ws(cnpj_limpo: str, data: Dict[str, Any]) -> ClienteCNPJDTO:
    """
    Converte o retorno da CNPJ.ws para ClienteCNPJDTO.
    """
    debug_print("Normalizando retorno da CNPJ.ws...")

    estabelecimento = data.get("estabelecimento") or {}

    razao_social = texto_limpo(data.get("razao_social"))
    nome_fantasia = texto_limpo(estabelecimento.get("nome_fantasia"))
    nome = razao_social or nome_fantasia

    if nome:
        debug_print("Nome OK")
        debug_print(f"Nome/Razão Social: {nome}")
    else:
        debug_error("CNPJ.ws retornou dados, mas sem razão social ou nome fantasia.")
        raise CNPJConsultaError(
            "CNPJ encontrado, mas sem razão social disponível no retorno da consulta."
        )

    telefone = juntar_ddd_telefone(
        estabelecimento.get("ddd1"),
        estabelecimento.get("telefone1"),
    )

    if telefone:
        debug_print("Telefone OK")
    else:
        debug_print("Telefone não encontrado no retorno da CNPJ.ws")

    email = texto_limpo(estabelecimento.get("email")).lower()

    if email:
        debug_print("E-mail OK")
        debug_print(f"E-mail encontrado: {email}")
    else:
        debug_print("E-mail não encontrado no retorno da CNPJ.ws")

    logradouro = texto_limpo(estabelecimento.get("logradouro"))
    numero = texto_limpo(estabelecimento.get("numero"))
    complemento = texto_limpo(estabelecimento.get("complemento"))
    bairro = texto_limpo(estabelecimento.get("bairro"))
    municipio = texto_limpo(get_nested(estabelecimento, "cidade", "nome"))
    uf = texto_limpo(get_nested(estabelecimento, "estado", "sigla"))
    cep = formatar_cep(estabelecimento.get("cep"))

    endereco = montar_endereco_padrao(
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
    )

    situacao = texto_limpo(estabelecimento.get("situacao_cadastral"))
    cnae = texto_limpo(get_nested(estabelecimento, "atividade_principal", "descricao"))

    dto = ClienteCNPJDTO(
        nome=nome,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        cpf_cnpj=formatar_cnpj(cnpj_limpo),
        cnpj_limpo=cnpj_limpo,
        telefone=telefone,
        whatsapp=telefone,
        email=email,
        endereco=endereco,
        cep=cep,
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        situacao=situacao,
        cnae=cnae,
        fonte="CNPJ.ws",
    )

    debug_print("DTO CNPJ.ws OK")
    return dto


def montar_dto_brasilapi(cnpj_limpo: str, data: Dict[str, Any]) -> ClienteCNPJDTO:
    """
    Converte o retorno da BrasilAPI para ClienteCNPJDTO.
    """
    debug_print("Normalizando retorno da BrasilAPI...")

    razao_social = texto_limpo(data.get("razao_social"))
    nome_fantasia = texto_limpo(data.get("nome_fantasia"))
    nome = razao_social or nome_fantasia

    if nome:
        debug_print("Nome OK")
        debug_print(f"Nome/Razão Social: {nome}")
    else:
        debug_error("BrasilAPI retornou dados, mas sem razão social ou nome fantasia.")
        raise CNPJConsultaError(
            "CNPJ encontrado, mas sem razão social disponível no retorno da consulta."
        )

    telefone = texto_limpo(
        data.get("ddd_telefone_1")
        or data.get("ddd_telefone_2")
        or data.get("telefone")
        or data.get("phone")
    )
    telefone = formatar_telefone(telefone)

    if telefone:
        debug_print("Telefone OK")
    else:
        debug_print("Telefone não encontrado no retorno da BrasilAPI")

    email = texto_limpo(data.get("email") or data.get("correio_eletronico")).lower()

    if email:
        debug_print("E-mail OK")
        debug_print(f"E-mail encontrado: {email}")
    else:
        debug_print("E-mail não encontrado no retorno da BrasilAPI")

    logradouro = texto_limpo(data.get("logradouro"))
    numero = texto_limpo(data.get("numero"))
    complemento = texto_limpo(data.get("complemento"))
    bairro = texto_limpo(data.get("bairro"))
    municipio = texto_limpo(data.get("municipio"))
    uf = texto_limpo(data.get("uf"))
    cep = formatar_cep(data.get("cep"))

    endereco = montar_endereco_padrao(
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        cep=cep,
    )

    situacao = texto_limpo(data.get("descricao_situacao_cadastral"))
    cnae = texto_limpo(data.get("cnae_fiscal_descricao"))

    dto = ClienteCNPJDTO(
        nome=nome,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        cpf_cnpj=formatar_cnpj(cnpj_limpo),
        cnpj_limpo=cnpj_limpo,
        telefone=telefone,
        whatsapp=telefone,
        email=email,
        endereco=endereco,
        cep=cep,
        logradouro=logradouro,
        numero=numero,
        complemento=complemento,
        bairro=bairro,
        municipio=municipio,
        uf=uf,
        situacao=situacao,
        cnae=cnae,
        fonte="BrasilAPI",
    )

    debug_print("DTO BrasilAPI OK")
    return dto


def consultar_cnpj_ws(cnpj_limpo: str, timeout: int = DEFAULT_TIMEOUT) -> ClienteCNPJDTO:
    """
    Consulta CNPJ na API pública CNPJ.ws.
    """
    debug_print("=" * 70)
    debug_print("Consultando CNPJ.ws...")
    debug_print("CNPJ.ws será usada como fonte principal")

    url = CNPJ_WS_URL.format(cnpj=cnpj_limpo)

    debug_print(f"URL da consulta: {url}")
    debug_print(f"Timeout configurado: {timeout} segundos")

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "MVP-Federal-Eventos/1.0",
            },
        )

        debug_print(f"Resposta CNPJ.ws recebida com status {response.status_code}")
        debug_print(
            f"Rate limit restante CNPJ.ws: "
            f"{response.headers.get('X-RateLimit-Remaining') or 'não informado'}"
        )

    except requests.Timeout as exc:
        debug_error("Tempo esgotado ao consultar CNPJ.ws.")
        raise CNPJConsultaError(
            "Tempo esgotado ao consultar o CNPJ. Tente novamente em alguns instantes."
        ) from exc

    except requests.ConnectionError as exc:
        debug_error("Falha de conexão ao consultar CNPJ.ws.")
        raise CNPJConsultaError(
            "Falha de conexão ao consultar o CNPJ. Verifique a internet e tente novamente."
        ) from exc

    except requests.RequestException as exc:
        debug_error(f"Erro genérico ao consultar CNPJ.ws: {exc}")
        raise CNPJConsultaError("Não foi possível consultar o CNPJ agora.") from exc

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError as exc:
            debug_error("CNPJ.ws retornou JSON inválido.")
            raise CNPJConsultaError("Resposta inválida recebida do serviço de CNPJ.") from exc

        debug_print("CNPJ.ws OK")
        return montar_dto_cnpj_ws(cnpj_limpo, data)

    if response.status_code == 404:
        debug_error("CNPJ não encontrado na CNPJ.ws.")
        raise CNPJConsultaError("CNPJ não encontrado.")

    if response.status_code == 400:
        debug_error("CNPJ inválido ou malformado segundo a CNPJ.ws.")
        raise CNPJConsultaError("CNPJ inválido ou malformado.")

    if response.status_code == 429:
        debug_error("Limite de consultas atingido na CNPJ.ws.")
        raise CNPJConsultaError(RATE_LIMIT_USER_MESSAGE)

    if response.status_code >= 500:
        debug_error("CNPJ.ws temporariamente indisponível.")
        raise CNPJConsultaError(
            "Serviço de CNPJ temporariamente indisponível. Tente novamente depois."
        )

    debug_error(f"Erro inesperado na CNPJ.ws. Status: {response.status_code}")
    raise CNPJConsultaError(
        f"Erro ao consultar CNPJ. Código de retorno: {response.status_code}."
    )


def consultar_cnpj_brasilapi(cnpj_limpo: str, timeout: int = DEFAULT_TIMEOUT) -> ClienteCNPJDTO:
    """
    Consulta CNPJ na BrasilAPI como fallback.
    """
    debug_print("=" * 70)
    debug_print("Consultando BrasilAPI...")
    debug_print("BrasilAPI será usada como fallback")

    url = BRASILAPI_CNPJ_URL.format(cnpj=cnpj_limpo)

    debug_print(f"URL da consulta: {url}")
    debug_print(f"Timeout configurado: {timeout} segundos")

    try:
        response = requests.get(url, timeout=timeout)

        debug_print(f"Resposta BrasilAPI recebida com status {response.status_code}")

    except requests.Timeout as exc:
        debug_error("Tempo esgotado ao consultar BrasilAPI.")
        raise CNPJConsultaError(
            "Tempo esgotado ao consultar o CNPJ. Tente novamente em alguns instantes."
        ) from exc

    except requests.ConnectionError as exc:
        debug_error("Falha de conexão ao consultar BrasilAPI.")
        raise CNPJConsultaError(
            "Falha de conexão ao consultar o CNPJ. Verifique a internet e tente novamente."
        ) from exc

    except requests.RequestException as exc:
        debug_error(f"Erro genérico ao consultar BrasilAPI: {exc}")
        raise CNPJConsultaError("Não foi possível consultar o CNPJ agora.") from exc

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError as exc:
            debug_error("BrasilAPI retornou JSON inválido.")
            raise CNPJConsultaError("Resposta inválida recebida do serviço de CNPJ.") from exc

        debug_print("BrasilAPI OK")
        return montar_dto_brasilapi(cnpj_limpo, data)

    if response.status_code == 404:
        debug_error("CNPJ não encontrado na BrasilAPI.")
        raise CNPJConsultaError("CNPJ não encontrado.")

    if response.status_code == 400:
        debug_error("CNPJ inválido ou malformado segundo a BrasilAPI.")
        raise CNPJConsultaError("CNPJ inválido ou malformado.")

    if response.status_code == 429:
        debug_error("Limite de consultas atingido na BrasilAPI.")
        raise CNPJConsultaError(RATE_LIMIT_USER_MESSAGE)

    if response.status_code >= 500:
        debug_error("BrasilAPI temporariamente indisponível.")
        raise CNPJConsultaError(
            "Serviço de CNPJ temporariamente indisponível. Tente novamente depois."
        )

    debug_error(f"Erro inesperado na BrasilAPI. Status: {response.status_code}")
    raise CNPJConsultaError(
        f"Erro ao consultar CNPJ. Código de retorno: {response.status_code}."
    )


def consultar_cnpj_com_fallback(cnpj_limpo: str) -> ClienteCNPJDTO:
    """
    Consulta CNPJ com CNPJ.ws como principal e BrasilAPI como fallback.

    Se ambas retornarem limite de requisição, a mensagem final será:
    "Aguarde 1 minuto e tente novamente"
    """
    erros: list[str] = []
    houve_rate_limit = False

    debug_print("Iniciando consulta com fallback...")

    try:
        return consultar_cnpj_ws(cnpj_limpo)
    except CNPJConsultaError as erro:
        mensagem = str(erro)
        erros.append(f"CNPJ.ws: {mensagem}")

        debug_error(f"CNPJ.ws falhou: {mensagem}")

        if mensagem == RATE_LIMIT_USER_MESSAGE:
            houve_rate_limit = True

    debug_print("Tentando fallback com BrasilAPI...")

    try:
        return consultar_cnpj_brasilapi(cnpj_limpo)
    except CNPJConsultaError as erro:
        mensagem = str(erro)
        erros.append(f"BrasilAPI: {mensagem}")

        debug_error(f"BrasilAPI falhou: {mensagem}")

        if mensagem == RATE_LIMIT_USER_MESSAGE:
            houve_rate_limit = True

    if houve_rate_limit:
        debug_error("Limite máximo de solicitação atingido nas APIs disponíveis.")
        raise CNPJConsultaError(RATE_LIMIT_USER_MESSAGE)

    debug_error("Todas as fontes de consulta falharam.")
    raise CNPJConsultaError(
        "Não foi possível consultar o CNPJ agora. Tente novamente em alguns instantes."
    )


def buscar_cliente_por_documento(documento: str) -> ClienteCNPJDTO:
    """
    Função principal para ser chamada pela tela.

    Regra:
    - CNPJ: consulta automática.
    - CPF: não consulta; retorna erro controlado.
    - Outro formato: retorna erro.
    """
    debug_print("Recebendo documento para busca automática...")

    documento_limpo = limpar_documento(documento)

    if len(documento_limpo) == 11:
        debug_error("Documento informado é CPF. Consulta automática bloqueada.")
        raise CNPJConsultaError(
            "Consulta automática disponível apenas para CNPJ. Para CPF, preencha manualmente."
        )

    if len(documento_limpo) != 14:
        debug_error("Documento informado não possui tamanho válido para CNPJ.")
        raise CNPJConsultaError(
            "Informe um CNPJ válido com 14 números para realizar a busca automática."
        )

    debug_print("Documento identificado como CNPJ")

    cnpj_limpo = validar_cnpj_basico(documento_limpo)

    dto_cache = buscar_no_cache(cnpj_limpo)

    if dto_cache:
        debug_print("Finalizando consulta")
        debug_print("Tudo certo via cache")
        return dto_cache

    debug_print("CNPJ não está no cache. Consultando APIs externas...")

    dto = consultar_cnpj_com_fallback(cnpj_limpo)

    salvar_cnpj_no_cache(cnpj_limpo, dto)

    debug_print("Resumo do retorno:")
    debug_print(f"- Fonte: {dto.fonte or 'não informado'}")
    debug_print(f"- Nome: {dto.nome or 'não informado'}")
    debug_print(f"- CNPJ: {dto.cpf_cnpj or 'não informado'}")
    debug_print(f"- Telefone: {dto.telefone or 'não informado'}")
    debug_print(f"- WhatsApp: {dto.whatsapp or 'não informado'}")
    debug_print(f"- E-mail: {dto.email or 'não informado'}")
    debug_print(f"- Endereço: {dto.endereco or 'não informado'}")
    debug_print(f"- Situação: {dto.situacao or 'não informado'}")
    debug_print(f"- CNAE: {dto.cnae or 'não informado'}")

    debug_print("Finalizando consulta")
    debug_print("Tudo certo")
    debug_print("=" * 70)

    return dto


def consultar_cnpj_para_formulario(cnpj: str) -> Dict[str, str]:
    """
    Atalho para uso direto no Streamlit.

    Retorna somente os campos necessários para preencher o formulário atual.
    """
    debug_print("Preparando consulta para preenchimento do formulário...")

    dto = buscar_cliente_por_documento(cnpj)

    form_dict = dto.to_form_dict()

    debug_print("Dicionário do formulário montado:")
    debug_print(f"- nome: {form_dict.get('nome') or 'não informado'}")
    debug_print(f"- cpf_cnpj: {form_dict.get('cpf_cnpj') or 'não informado'}")
    debug_print(f"- telefone: {form_dict.get('telefone') or 'não informado'}")
    debug_print(f"- whatsapp: {form_dict.get('whatsapp') or 'não informado'}")
    debug_print(f"- email: {form_dict.get('email') or 'não informado'}")
    debug_print(f"- endereco: {form_dict.get('endereco') or 'não informado'}")

    return form_dict


def consultar_cnpj_completo(cnpj: str) -> Dict[str, str]:
    """
    Atalho para uso futuro com banco de dados.

    Retorna todos os campos normalizados.
    """
    debug_print("Preparando consulta completa para uso futuro no banco...")

    dto = buscar_cliente_por_documento(cnpj)

    completo = dto.to_dict()

    debug_print("Dicionário completo montado com sucesso")

    return completo