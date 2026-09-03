from agent.check import _explain_http_error, suggest


def test_suggest_filters_out_non_chat_models():
    models = [
        "llama-3.3-70b-versatile",
        "whisper-large-v3",
        "meta-llama/llama-guard-4-12b",
        "playai-tts",
        "openai/gpt-oss-120b",
    ]
    assert suggest(models) == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]


def test_explain_http_error_identifies_a_bad_key():
    assert "key was rejected" in _explain_http_error(401, "")


def test_explain_http_error_identifies_a_retired_model():
    assert "no longer exists" in _explain_http_error(400, '{"error":{"code":"model_not_found"}}')


def test_explain_http_error_identifies_rate_limiting():
    assert "rate limited" in _explain_http_error(429, "").lower()


def test_explain_http_error_falls_back_to_the_raw_body():
    assert "HTTP 500" in _explain_http_error(500, "upstream exploded")
