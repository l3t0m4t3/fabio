from abc import ABC, abstractmethod
from enum import IntEnum
import logging

logger = logging.getLogger("log")
logger.setLevel(logging.INFO)
arquivo = logging.FileHandler("log.txt", encoding="utf-8")
arquivo.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%d/%m/%Y %H:%M:%S")
)
logger.addHandler(arquivo)


class Mediador(ABC):
    @abstractmethod
    def registrar(self, caixa: "Caixa") -> None:
        ...

    @abstractmethod
    def solicitar_cedulas(self, solicitante: "Caixa", valor: int) -> None:
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



class Caixa:
    ESTOQUE_PADRAO = {
        Cedula.duzentos: 3, Cedula.cem: 5, Cedula.cinquenta: 5,
        Cedula.vinte: 10, Cedula.dez: 10, Cedula.cinco: 10, Cedula.dois: 30,
    }

    def __init__(self, nome: str, banco: Mediador, cedulas: dict | None = None):
        self.nome = nome
        origem = self.ESTOQUE_PADRAO if cedulas is None else cedulas
        self._cedulas = self._validar_cedulas(origem)  # valida ANTES de registrar
        self.mediador: Mediador = banco
        banco.registrar(self)
        logger.info(f"[{self.nome}] criado com estoque {self._cedulas}")

    @staticmethod
    def _validar_cedulas(cedulas: dict) -> dict[Cedula, int]:
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
        
    @staticmethod
    def calcular_notas(valor: int, estoque: dict) -> dict | None:
        """Menor número de notas para o valor, respeitando o estoque.
        Retorna None se for impossível."""
        notas = sorted(estoque, reverse=True)
        memo = {}

        def resolver(i, restante):
            if restante == 0:
                return {}
            if i == len(notas):
                return None
            if (i, restante) in memo:
                return memo[(i, restante)]

            nota = notas[i]
            max_qtd = min(restante // nota, estoque[nota])
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

        return resolver(0, valor)

    @property
    def estoque(self) -> dict:
        return dict(self._cedulas)  # cópia, protege o estado interno

    def sacar(self, valor: int) -> dict:
        if valor <= 0:
            logger.warning(f"[{self.nome}] saque recusado: valor inválido ({valor})")
            raise ValueError("O valor deve ser positivo")

        logger.info(f"[{self.nome}] saque solicitado: R$ {valor}")
        plano = self.calcular_notas(valor, self._cedulas)

        if plano is None:
            logger.info(f"[{self.nome}] sem cédulas suficientes, pedindo ao banco...")
            self.mediador.solicitar_cedulas(self, valor)

            plano = self.calcular_notas(valor, self._cedulas)
            if plano is None:
                logger.error(
                    f"[{self.nome}] não foi possível obter as cédulas para R$ {valor}"
                )
                raise ValueError(f"{self.nome}: não foi possível obter as cédulas")

        for nota, qtd in plano.items():
            self._cedulas[nota] -= qtd

        logger.info(
            f"[{self.nome}] saque de R$ {valor} concluído: {plano} | estoque: {self._cedulas}"
        )
        return dict(sorted(plano.items(), reverse=True))

    # usados apenas pelo Banco
    def receber_cedulas(self, cedulas: dict) -> None:
        for nota, qtd in cedulas.items():
            self._cedulas[nota] = self._cedulas.get(nota, 0) + qtd

    def entregar_cedulas(self, cedulas: dict) -> None:
        for nota, qtd in cedulas.items():
            self._cedulas[nota] -= qtd


class Banco(Mediador):
    def __init__(self):
        self._caixas: list[Caixa] = []

    def registrar(self, caixa: Caixa) -> None:
        if caixa not in self._caixas:
            self._caixas.append(caixa)

    def solicitar_cedulas(self, solicitante: Caixa, valor: int) -> None:
        outros = [c for c in self._caixas if c is not solicitante]

        pool = {}
        for caixa in self._caixas:
            for nota, qtd in caixa.estoque.items():
                pool[nota] = pool.get(nota, 0) + qtd

        plano = solicitante.calcular_notas(valor, pool)
        if plano is None:
            logger.error(f"[Banco] nenhum caixa da rede consegue sacar R$ {valor}")
            raise ValueError(f"Nenhum caixa da rede consegue sacar {valor}")

        for nota, qtd in plano.items():
            faltante = qtd - solicitante.estoque.get(nota, 0)
            if faltante <= 0:
                continue


            for doador in sorted(
                outros, key=lambda c: c.estoque.get(nota, 0), reverse=True
            ):
                pega = min(faltante, doador.estoque.get(nota, 0))
                if pega > 0:
                    doador.entregar_cedulas({nota: pega})
                    solicitante.receber_cedulas({nota: pega})
                    logger.info(
                        f"[Banco] {doador.nome} -> {solicitante.nome}: {pega}x R$ {nota}"
                    )
                    faltante -= pega
                if faltante == 0:
                    break

