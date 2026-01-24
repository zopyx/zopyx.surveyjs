import orjson


def json_response(
    response,
    payload,
    status=200,
    content_type="application/json",
    dumps_options=None,
):
    response.setStatus(status)
    response.setHeader("content-type", content_type)
    if dumps_options is None:
        response.write(orjson.dumps(payload))
    else:
        response.write(orjson.dumps(payload, option=dumps_options))


def json_error(response, status, error, message=None, extra=None):
    payload = {"error": error}
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    json_response(response, payload, status=status)


def parse_json_body(request):
    raw_body = request.get("BODY", b"")
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    if not raw_body:
        return None
    try:
        return orjson.loads(raw_body)
    except orjson.JSONDecodeError:
        return None
