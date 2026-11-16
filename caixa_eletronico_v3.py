from abc import ABC, abstractmethod
from enum import IntEnum
from pathlib import Path
from typing import NamedTuple
import getpass
import hmac
import json
import logging
import os


def configurar_log(arquivo: str = "log.txt") -> None:
    logging.basicConfig(
        filename=arquivo,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-7s | %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )


def reais(valor: int) -> str:
    return f"R$ {valor:,}".replace(",", ".")


def plural(quantidade: int) -> str:
    return "s" if quantidade > 1 else ""


class Mediador(ABC):
    @abstractmethod
    def registrar(self, caixa: "Caixa") -> None:
        ...

    @abstractmethod
    def solicitar_cedulas(self, solicitante: "Caixa", valor: int) -> list["Emprestimo"]:
        ...


class Cedula(IntEnum):
    dois = 2
    cinco = 5
    dez = 10
    vinte = 20
    cinquenta = 50
    cem = 100
    duzentos = 200

    def __repr__(self) -> str:
        return str(self.name)

    @property
    def rotulo(self) -> str:
        return f"{self.name} (R$ {self.value})"


class Emprestimo(NamedTuple):
    doador: str
    cedula: Cedula
    quantidade: int


class Estoque:

    def __init__(self, cedulas: "Estoque | dict[Cedula, int] | None" = None):
        self._itens: dict[Cedula, int] = self._normalizar(cedulas or {})

    @staticmethod
    def _normalizar(cedulas: "Estoque | dict[Cedula, int]") -> dict[Cedula, int]:
        if isinstance(cedulas, Estoque):
            return dict(cedulas._itens)
        if not isinstance(cedulas, dict):
            raise TypeError("As cédulas devem ser um dicionário {Cedula: quantidade}")

        validadas = {}
        for nota, qtd in cedulas.items():
            if not isinstance(nota, Cedula):
                raise TypeError(
                    f"Chave inválida {nota!r}: use um membro de Cedula (ex.: Cedula.cem)"
                )
            if isinstance(qtd, bool) or not isinstance(qtd, int) or qtd < 0:
                raise ValueError(f"Quantidade inválida para {nota.name}: {qtd!r}")
            validadas[nota] = qtd
        return validadas

    def quantidade(self, nota: Cedula) -> int:
        return self._itens.get(nota, 0)

    @property
    def total(self) -> int:
        return sum(nota * qtd for nota, qtd in self._itens.items())

    def adicionar(self, outro: "Estoque | dict[Cedula, int]") -> None:
        for nota, qtd in self._normalizar(outro).items():
            self._itens[nota] = self.quantidade(nota) + qtd

    def retirar(self, outro: "Estoque | dict[Cedula, int]") -> None:
        itens = self._normalizar(outro)
        for nota, qtd in itens.items():
            if qtd > self.quantidade(nota):
                raise ValueError(
                    f"estoque insuficiente de {nota.name}: "
                    f"pedido {qtd}, disponível {self.quantidade(nota)}"
                )
        for nota, qtd in itens.items():
            self._itens[nota] -= qtd

    def copia(self) -> "Estoque":
        return Estoque(self)

    def como_dict(self) -> dict[Cedula, int]:
        return dict(self._itens)

    def items(self) -> list[tuple[Cedula, int]]:
        return sorted(self._itens.items(), reverse=True)

    def __add__(self, outro: "Estoque | dict[Cedula, int]") -> "Estoque":
        soma = self.copia()
        soma.adicionar(outro)
        return soma

    def __eq__(self, outro: object) -> bool:
        if not isinstance(outro, Estoque):
            return NotImplemented
        return {n: q for n, q in self._itens.items() if q} == {
            n: q for n, q in outro._itens.items() if q
        }

    def __repr__(self) -> str:
        itens = ", ".join(f"{nota!r}: {qtd}" for nota, qtd in self.items())
        return "{" + itens + "}"


class ResultadoSaque(NamedTuple):
    notas: Estoque
    emprestimos: list[Emprestimo]

    @property
    def pediu_ao_banco(self) -> bool:
        return bool(self.emprestimos)


class Caixa:
    ESTOQUE_PADRAO = {
        Cedula.duzentos: 3,
        Cedula.cem: 5,
        Cedula.cinquenta: 5,
        Cedula.vinte: 10,
        Cedula.dez: 10,
        Cedula.cinco: 10,
        Cedula.dois: 30,
    }

    def __init__(
        self,
        nome: str,
        banco: Mediador,
        estoque: Estoque | dict[Cedula, int] | None = None,
    ):
        self.nome = nome
        self._log = logging.getLogger(nome)
        origem = self.ESTOQUE_PADRAO if estoque is None else estoque
        self._estoque = Estoque(origem)  # valida e copia ANTES de registrar
        self.mediador: Mediador = banco
        banco.registrar(self)
        self._log.info(
            f"criado: estoque {self._estoque} | total {reais(self._estoque.total)}"
        )

    @property
    def estoque(self) -> Estoque:
        return self._estoque.copia()  # cópia, protege o estado interno

    @staticmethod
    def calcular_notas(valor: int, estoque: Estoque) -> Estoque | None:
        disponivel = estoque.como_dict()
        notas = sorted(disponivel, reverse=True)
        memo = {}

        def resolver(i, restante):
            if restante == 0:
                return {}
            if i == len(notas):
                return None
            if (i, restante) in memo:
                return memo[(i, restante)]

            nota = notas[i]
            max_qtd = min(restante // nota, disponivel[nota])
            melhor = None

            for qtd in range(max_qtd, -1, -1):
                sub = resolver(i + 1, restante - qtd * nota)
                if sub is not None:
                    candidato = dict(sub)
                    if qtd > 0:
                        candidato[nota] = qtd
                    if melhor is None or sum(candidato.values()) < sum(melhor.values()):
                        melhor = candidato

            memo[(i, restante)] = melhor
            return melhor

        resultado = resolver(0, valor)
        return None if resultado is None else Estoque(resultado)

    def sacar(self, valor: int) -> ResultadoSaque:
        if valor <= 0:
            self._log.warning(f"saque recusado: valor inválido ({reais(valor)})")
            raise ValueError("O valor deve ser positivo")

        self._log.info(f"saque solicitado: {reais(valor)}")
        emprestimos: list[Emprestimo] = []
        plano = self.calcular_notas(valor, self._estoque)

        if plano is None:
            self._log.info(
                f"estoque insuficiente para {reais(valor)}: solicitando cédulas ao banco"
            )
            emprestimos = self.mediador.solicitar_cedulas(self, valor)

            plano = self.calcular_notas(valor, self._estoque)
            if plano is None:
                self._log.error(
                    f"inconsistência: banco atendeu o pedido, mas {reais(valor)} "
                    f"continua impossível"
                )
                raise ValueError(f"{self.nome}: não foi possível obter as cédulas")

        self._estoque.retirar(plano)
        self._log.info(
            f"saque concluído: {reais(valor)} em {plano} | estoque restante: {self._estoque}"
        )
        return ResultadoSaque(plano, emprestimos)

    def reabastecer(self, cedulas: Estoque | dict[Cedula, int]) -> None:
        """Adiciona cédulas ao caixa (operação de administrador)."""
        novas = Estoque(cedulas)  # valida antes de tocar no estoque
        if novas.total == 0:
            self._log.warning("reabastecimento recusado: nenhuma cédula informada")
            raise ValueError("Informe ao menos uma cédula para adicionar")

        self._estoque.adicionar(novas)
        self._log.info(
            f"reabastecido: +{novas} ({reais(novas.total)}) | estoque: {self._estoque}"
        )

    def receber_cedulas(self, cedulas: Estoque) -> None:
        self._estoque.adicionar(cedulas)

    def entregar_cedulas(self, cedulas: Estoque) -> None:
        self._estoque.retirar(cedulas)


class Banco(Mediador):
    def __init__(self):
        self._caixas: list[Caixa] = []
        self._log = logging.getLogger("Banco")

    @property
    def caixas(self) -> tuple[Caixa, ...]:
        return tuple(self._caixas)

    def registrar(self, caixa: Caixa) -> None:
        if caixa not in self._caixas:
            self._caixas.append(caixa)
            self._log.info(f"{caixa.nome} registrado na rede")

    def solicitar_cedulas(self, solicitante: Caixa, valor: int) -> list[Emprestimo]:
        outros = [c for c in self._caixas if c is not solicitante]

        pool = sum((c.estoque for c in self._caixas), Estoque())

        plano = solicitante.calcular_notas(valor, pool)
        if plano is None:
            self._log.warning(
                f"pedido de {solicitante.nome} recusado: "
                f"a rede não consegue formar {reais(valor)}"
            )
            raise ValueError(
                f"{solicitante.nome} não tem cédulas suficientes e "
                f"a rede também não consegue formar {reais(valor)}"
            )

        emprestimos: list[Emprestimo] = []
        proprio = solicitante.estoque
        for nota, qtd in plano.items():
            faltante = qtd - proprio.quantidade(nota)
            if faltante <= 0:
                continue

            for doador in sorted(
                outros, key=lambda c: c.estoque.quantidade(nota), reverse=True
            ):
                pega = min(faltante, doador.estoque.quantidade(nota))
                if pega > 0:
                    emprestimo = Estoque({nota: pega})
                    doador.entregar_cedulas(emprestimo)
                    solicitante.receber_cedulas(emprestimo)
                    emprestimos.append(Emprestimo(doador.nome, nota, pega))
                    self._log.info(
                        f"empréstimo: {doador.nome} -> {solicitante.nome}: "
                        f"{pega}x {nota.rotulo}"
                    )
                    faltante -= pega
                if faltante == 0:
                    break

        return emprestimos


# ---------------------------------------------------------------------------
# Persistência em JSON
# ---------------------------------------------------------------------------
class ErroPersistencia(Exception):
    pass


class RepositorioJson:
    """Guarda o estoque de todos os caixas em um único arquivo JSON.

    Formato:
        {"versao": 1, "caixas": {"Caixa 1": {"duzentos": 3, "cem": 5, ...}}}
    As cédulas são gravadas pelo nome, que é legível e não depende do valor.
    """

    VERSAO = 1

    def __init__(self, caminho: str = "caixas.json"):
        self.caminho = Path(caminho)
        self._log = logging.getLogger("Dados")

    def salvar(self, banco: Banco) -> None:
        dados = {
            "versao": self.VERSAO,
            "caixas": {
                caixa.nome: {nota.name: qtd for nota, qtd in caixa.estoque.items()}
                for caixa in banco.caixas
            },
        }
        # grava em arquivo temporário e troca no final: se algo falhar no meio
        # da escrita, o arquivo anterior continua íntegro
        temporario = self.caminho.with_name(self.caminho.name + ".tmp")
        try:
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self.caminho)
        except OSError as erro:
            self._log.error(f"não foi possível salvar {self.caminho}: {erro}")
            raise ErroPersistencia(f"não foi possível salvar os dados ({erro})") from erro

    def carregar(self) -> dict[str, Estoque]:
        """Devolve {nome do caixa: Estoque}. Sem arquivo, devolve {}."""
        if not self.caminho.exists():
            self._log.info(f"{self.caminho} não encontrado: usando estoque padrão")
            return {}

        try:
            with open(self.caminho, encoding="utf-8") as arquivo:
                caixas = self._interpretar(json.load(arquivo))
        except (OSError, ValueError, TypeError) as erro:  # JSONDecodeError é ValueError
            copia = self._isolar_arquivo()
            detalhe = f" Uma cópia foi guardada em {copia}." if copia else ""
            self._log.error(f"dados inválidos em {self.caminho}: {erro}.{detalhe}")
            raise ErroPersistencia(
                f"o arquivo {self.caminho} está inválido ({erro}).{detalhe}"
            ) from erro

        self._log.info(f"dados carregados de {self.caminho}: {', '.join(caixas)}")
        return caixas

    def _interpretar(self, bruto: object) -> dict[str, Estoque]:
        if not isinstance(bruto, dict) or not isinstance(bruto.get("caixas"), dict):
            raise ValueError("formato inesperado")
        if bruto.get("versao") != self.VERSAO:
            raise ValueError(f"versão não suportada: {bruto.get('versao')!r}")

        caixas = {}
        for nome, cedulas in bruto["caixas"].items():
            if not isinstance(cedulas, dict):
                raise ValueError(f"estoque inválido para {nome}")
            try:
                itens = {Cedula[chave]: qtd for chave, qtd in cedulas.items()}
            except KeyError as erro:
                raise ValueError(f"cédula desconhecida em {nome}: {erro.args[0]}") from None
            caixas[nome] = Estoque(itens)  # valida as quantidades
        return caixas

    def _isolar_arquivo(self) -> Path | None:
        """Move o arquivo inválido para o lado, para não ser sobrescrito."""
        destino = self.caminho.with_name(self.caminho.name + ".corrompido")
        try:
            os.replace(self.caminho, destino)
            return destino
        except OSError:
            return None


#SENHA
SENHA_ADMIN = os.environ.get("CAIXA_SENHA_ADMIN", "admin123")


def autenticar_admin(tentativas: int = 3) -> bool:
    log = logging.getLogger("Sistema")
    for _ in range(tentativas):
        digitada = getpass.getpass("Senha do administrador: ")
        if hmac.compare_digest(digitada.encode(), SENHA_ADMIN.encode()):
            log.info("administrador autenticado")
            return True
        print("Senha incorreta.")
        log.warning("tentativa de acesso de administrador com senha incorreta")

    print("Número máximo de tentativas excedido.")
    log.warning("acesso de administrador bloqueado: excesso de tentativas")
    return False


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
def exibir_estoque(estoque: Estoque) -> None:
    for nota, qtd in estoque.items():
        print(f"  {nota.rotulo}: {qtd}")
    print(f"  total: {reais(estoque.total)}")


def salvar_dados(repo: RepositorioJson, banco: Banco) -> None:
    try:
        repo.salvar(banco)
    except ErroPersistencia as erro:
        print(f"Aviso: {erro}")


def operacao_sacar(cx: Caixa) -> bool:
    """Retorna True se o estado dos caixas pode ter mudado (e deve ser salvo)."""
    entrada = input("Informe o valor a ser sacado:\n")
    if not entrada.isdigit():
        print("Digite apenas números inteiros.")
        return False

    try:
        resultado = cx.sacar(int(entrada))
    except ValueError as erro:
        print(f"Não foi possível sacar: {erro}")
        return True  # um empréstimo pode ter movido cédulas antes da falha

    if resultado.pediu_ao_banco:
        print(f"O {cx.nome} não tinha cédulas suficientes e solicitou ao banco:")
        for emp in resultado.emprestimos:
            print(
                f"  {emp.quantidade} cédula{plural(emp.quantidade)} de "
                f"{emp.cedula.name} reais "
                f"(emprestada{plural(emp.quantidade)} pelo {emp.doador})"
            )

    print("Foi sacado:")
    for nota, qtd in resultado.notas.items():
        print(f"{qtd} cédula{plural(qtd)} de {nota.name} reais")
    return True


def operacao_admin(cx: Caixa) -> bool:
    """Retorna True se cédulas foram adicionadas (e o estado deve ser salvo)."""
    if not autenticar_admin():
        return False

    print(f"Modo administrador: adicionar cédulas ao {cx.nome}")
    print("Estoque atual:")
    exibir_estoque(cx.estoque)

    novas = Estoque()
    valores = ", ".join(str(c.value) for c in Cedula)
    while True:
        entrada = input(f"Valor da cédula ({valores}) ou Enter para concluir:\n")
        if entrada == "":
            break
        try:
            if not entrada.isdigit():
                raise ValueError
            cedula = Cedula(int(entrada))
        except ValueError:
            print("Cédula inválida, tente novamente.")
            continue

        quantidade = input(f"Quantas cédulas de {cedula.name} (R$ {cedula.value}) adicionar?\n")
        if not quantidade.isdigit() or int(quantidade) == 0:
            print("Quantidade inválida, tente novamente.")
            continue
        novas.adicionar({cedula: int(quantidade)})

    try:
        cx.reabastecer(novas)
    except ValueError as erro:
        print(f"Nada foi adicionado: {erro}")
        return False

    print(f"Adicionado {reais(novas.total)} ao {cx.nome}. Novo estoque:")
    exibir_estoque(cx.estoque)
    return True


def main() -> None:
    configurar_log()
    log = logging.getLogger("Sistema")
    repo = RepositorioJson()

    try:
        dados = repo.carregar()
    except ErroPersistencia as erro:
        print(f"Aviso: {erro}\nIniciando com o estoque padrão.\n")
        dados = {}

    banco = Banco()
    caixas = {}
    for numero in (1, 2, 3):
        nome = f"Caixa {numero}"
        caixas[numero] = Caixa(nome, banco, dados.get(nome))

    salvar_dados(repo, banco)
    log.info("sistema iniciado")

    while True:
        print("Você está em um banco. Escolha um caixa.")
        escolha = input(
            "CAIXA 1 ---- CAIXA 2 ---- CAIXA 3 (escolha 1, 2 ou 3, ou 0 para encerrar):\n"
        )
        if escolha == "0":
            print("Encerrando. Até logo!")
            log.info("sistema encerrado")
            break
        if not escolha.isdigit() or int(escolha) not in caixas:
            print("Caixa inválido, tente novamente.\n")
            continue

        cx = caixas[int(escolha)]
        while True:
            print("Agora escolha a operação")
            operacao = input("1 - sacar\n2 - sair\n3 - administrador (adicionar cédulas)\n")
            if operacao == "2":
                break
            elif operacao == "1":
                alterou = operacao_sacar(cx)
            elif operacao == "3":
                alterou = operacao_admin(cx)
            else:
                print("Operação inválida, tente novamente.")
                continue

            if alterou:
                salvar_dados(repo, banco)

if __name__ == '__main__':
  main()