from fastapi import Request, status
from fastapi.responses import JSONResponse

from src.core.logging import logger


class VaakException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class IntegrationNotConfiguredError(VaakException):
    def __init__(self, service_name: str):
        super().__init__(
            message=f"Integration '{service_name}' is not configured. Please supply required credentials.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def vaak_exception_handler(request: Request, exc: VaakException) -> JSONResponse:
    logger.warning(f"VaakException on {request.url.path}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.__class__.__name__, "message": exc.message}},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error processing {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}
        },
    )
