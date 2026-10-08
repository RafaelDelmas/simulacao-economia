from pydantic import BaseModel, Field


class ProdutoraComprar(BaseModel):
    """Compra a produtora de uma commodity (uma por commodity por jogador)."""

    commodity_id: int = Field(..., ge=1)


class ProdutoraOut(BaseModel):
    """Estado de uma produtora do jogador (payload do GET e das ações)."""

    id: int
    commodity_id: int
    name: str
    emoji: str
    nome: str
    nivel: int
    nivel_max: int
    ativa: bool
    divida: float
    energia: float
    energia_max: float
    energia_regen_por_segundo: float
    producao_dia: float
    cap_diario: float
    lote_min: int
    lote_max: int
    custo_insumo_unidade: float
    custo_insumo_lote: float
    manutencao_dia: float
    custo_melhoria: float | None  # None no nível máximo
    cooldown_segundos: float
    # Epoch da próxima unidade de energia e do fim do cooldown (UI sem drift).
    proxima_energia_em: float | None
    proximo_clique_em: float | None
    # Epoch de quando o dia de jogo vira (cap zera e manutenção é cobrada).
    dia_vence_em: float
    ciclo_em: float


class ProdutoraProduzir(BaseModel):
    """Resultado de um clique — o estoque já entrou na carteira."""

    produzida: ProdutoraOut
    unidades: float
    jackpot: bool
    custo_insumo: float
    saldo: float
    posicao_quantidade: float
