"""HTTP helpers for JSON request parsing and response rendering."""

import logging
import traceback

import orjson


# Generic error messages that are safe to expose to clients
_GENERIC_ERROR_MESSAGES = {
    "invalid_token": "Authentication failed. Please try again.",
    "token_generation_failed": "Service temporarily unavailable. Please try again later.",
    "validation_error": "Invalid input. Please check your data and try again.",
    "internal_error": "An error occurred. Please try again or contact support.",
}


def safe_json_error(
    response,
    status: int,
    error_code: str,
    public_message: str = None,
    exc: Exception = None,
    logger=None,
):
    """Log full error details internally and return only generic, safe error messages to the client.

    This function ensures that sensitive information (file paths, internal details,
    raw exception messages) is never exposed to the client while still logging
    comprehensive error details for debugging purposes.

    :param response: The Zope response object.
    :param status: HTTP status code to return.
    :param error_code: A short, machine-readable error identifier (e.g., 'invalid_token').
    :param public_message: Optional custom public message. If not provided, a generic
                           message will be looked up from _GENERIC_ERROR_MESSAGES.
    :param exc: Optional exception instance to log with full traceback.
    :param logger: Optional logger instance. If not provided, uses the module logger.
    """
    # Use module logger if none provided
    if logger is None:
        logger = logging.getLogger(__name__)

    # Determine the public message (safe for clients)
    if public_message is None:
        public_message = _GENERIC_ERROR_MESSAGES.get(
            error_code, _GENERIC_ERROR_MESSAGES["internal_error"]
        )

    # Log full error details internally (never exposed to client)
    if exc is not None:
        tb_str = traceback.format_exception(type(exc), exc, exc.__traceback__)
        logger.error(
            "Error [%s]: %s\nTraceback:\n%s",
            error_code,
            str(exc),
            "".join(tb_str),
        )
    else:
        logger.error("Error [%s]: %s", error_code, public_message)

    # Set error header for clients that cannot parse JSON body
    try:
        response.setHeader("X-Survey-Error", error_code)
    except Exception:
        pass

    # Build safe payload (never contains internal details)
    payload = {
        "error": error_code,
        "message": public_message,
    }

    json_response(response, payload, status=status)


def json_response(
    response,
    payload,
    status=200,
    content_type="application/json",
    dumps_options=None,
):
    """Write a JSON payload to the Zope response object."""
    response.setStatus(status)
    response.setHeader("content-type", content_type)
    if dumps_options is None:
        response.write(orjson.dumps(payload))
    else:
        response.write(orjson.dumps(payload, option=dumps_options))


def json_error(response, status, error, message=None, extra=None):
    """Write a standardized JSON error response."""
    # Expose the error key for clients that cannot parse the JSON body.
    try:
        response.setHeader("X-Survey-Error", error)
    except Exception:
        pass
    payload = {"error": error}
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    json_response(response, payload, status=status)


def parse_json_body(request):
    """Parse a JSON request body and return ``None`` on invalid input."""
    raw_body = request.get("BODY", b"")
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    if not raw_body:
        return None
    try:
        return orjson.loads(raw_body)
    except orjson.JSONDecodeError:
        return None
