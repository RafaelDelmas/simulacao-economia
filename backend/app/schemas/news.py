from pydantic import BaseModel, Field


class NewsDisparar(BaseModel):
    """Dispara uma carta de evento na hora (mestre de cena).

    Sem `id` sorteia como o automático; com `id` dispara aquela carta
    específica mesmo que tenha saído nas 3 últimas.
    """

    id: str | None = Field(None, max_length=64)
