from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação (lidas do ambiente/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Simulação Econômica API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Banco de dados
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "simulacao"
    db_user: str = "simulacao"
    db_password: str = "simulacao"

    # Autenticação
    admin_username: str = "admin"
    admin_password: str = "admin"
    jwt_secret: str = "troque-este-segredo-em-producao"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12  # 12 horas

    # Configurações do jogo
    jogo_inicial_saldo: float = 1000.0  # Saldo inicial de cada usuário
    bots_total: int = 1200              # Total de bots ativos
    bots_lotes: int = 10                # Número de lotes de bots
    bots_por_lote: int = 120            # Bots por lote
    bot_tick_ms: int = 100              # Loop assíncrono de bots (ms)
    taxa_inflacao_percentual: float = 0.5  # Taxa % aplicada a cada transição
    taxa_sink_interval_minutos: int = 60  # Intervalo para taxa de carga perdida (min)

    # Manutenção do banco — prune de orders (app/core/market/prune.py)
    ordem_ttl_minutos: int = 5           # ordem de BOT (user_id NULL) não executada expira em X min
    ordem_ttl_jogador_minutos: int = 600 # ordem de JOGADOR expira em X min (600 = 10 h)
    jogador_ordens_abertas_max: int = 10 # máximo de ordens abertas por jogador (global)
    historico_commodities_max: int = 500  # ordens preenchidas guardadas por commodity
    prune_intervalo_segundos: int = 60    # periodicidade do prune automático

    # Gráficos de preço — amostras em price_ticks (engine + prune)
    preco_tick_segundos: int = 3          # frequência da amostra de preço
    historico_precos_max: int = 400       # amostras guardadas por commodity
    preco_amplitude_percentual: float = 30.0  # faixa do preço em torno da base
    preco_reversao_percentual: float = 20.0   # puxada do preço pro nominal (0 = nenhuma)

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()