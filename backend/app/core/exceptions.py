class AppError(Exception):
    """Erro de aplicação com mensagem amigável e código HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str = "Recurso não encontrado"):
        super().__init__(message, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflito de dados"):
        super().__init__(message, status_code=409)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Não autenticado"):
        super().__init__(message, status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Acesso negado"):
        super().__init__(message, status_code=403)
