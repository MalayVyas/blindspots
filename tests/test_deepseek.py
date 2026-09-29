"""DeepSeek adapter tests. No network, no key, no cost: httpx.MockTransport
stands in for the API and returns whatever each test needs."""

import json

import httpx
import pytest

from blindspots.providers.base import ProviderError
from blindspots.providers.deepseek import DeepSeek, build_request

MSGS = [{"role": "user", "content": "Say hi."}]
ARGS = dict(model="deepseek-flash", max_tokens=100, temperature=0.0, thinking="disabled")


def usage(prompt=120, hit=64, miss=56, completion=10, reasoning=None, nested=True):
    u = {"prompt_tokens": prompt, "completion_tokens": completion,
         "total_tokens": prompt + completion}
    cache = {"prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": miss}
    if nested:
        u["prompt_tokens_details"] = cache
    else:
        u.update(cache)
    if reasoning is not None:
        u["completion_tokens_details"] = {"reasoning_tokens": reasoning}
    return u


def body(u=None, content="Hi.", finish="stop", reasoning_content=None):
    msg = {"role": "assistant", "content": content}
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    return {"id": "x", "model": "deepseek-flash",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": u if u is not None else usage()}


def client(handler):
    return DeepSeek(api_key="test-key", transport=httpx.MockTransport(handler))


def replying(payload, status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)
    return handler


# ---------------------------------------------------------------- request

def test_request_pins_every_setting():
    seen = []
    client(replying(body(), seen=seen)).complete(MSGS, **ARGS)
    sent = json.loads(seen[0].content)
    assert sent == {"model": "deepseek-flash", "messages": MSGS, "max_tokens": 100,
                    "temperature": 0.0, "thinking": {"type": "disabled"}, "stream": False}
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert seen[0].url.path == "/chat/completions"


def test_reasoning_effort_nested_in_thinking():
    b = build_request(MSGS, model="deepseek-flash", max_tokens=10, temperature=1.0,
                      thinking="enabled", reasoning_effort="low")
    assert b["thinking"] == {"type": "enabled", "reasoning_effort": "low"}


@pytest.mark.parametrize("bad", [
    dict(model="deepseek-chat"),                       # retired name
    dict(max_tokens=0),
    dict(max_tokens=400_000),
    dict(temperature=2.5),
    dict(thinking="auto"),
    dict(reasoning_effort="low"),                      # effort without thinking
])
def test_bad_requests_refused_before_sending(bad):
    seen = []
    with pytest.raises(ProviderError):
        client(replying(body(), seen=seen)).complete(MSGS, **{**ARGS, **bad})
    assert seen == []   # nothing went over the network


def test_missing_key_refused(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        DeepSeek()


# ---------------------------------------------------------------- response

def test_usage_and_cost_read_back():
    c = client(replying(body())).complete(MSGS, **ARGS)
    assert c.content == "Hi."
    assert (c.usage.input_tokens, c.usage.cache_hit_tokens, c.usage.cache_miss_tokens,
            c.usage.output_tokens) == (120, 64, 56, 10)
    expected_ref = (64 * 0.003 + 56 * 0.15 + 10 * 0.60) / 1e6
    assert c.reference_usd == pytest.approx(expected_ref)
    assert c.billed_usd == pytest.approx(expected_ref * (2 if c.peak else 1))
    assert c.response["id"] == "x"       # raw JSON kept for the transcript
    assert c.request["thinking"] == {"type": "disabled"}
    assert not c.truncated


def test_top_level_cache_fields_accepted():
    c = client(replying(body(usage(nested=False)))).complete(MSGS, **ARGS)
    assert c.usage.cache_hit_tokens == 64


def test_cache_fields_missing_is_an_error_not_zero():
    u = usage()
    del u["prompt_tokens_details"]
    with pytest.raises(ProviderError, match="no prompt_cache"):
        client(replying(body(u))).complete(MSGS, **ARGS)


def test_cache_fields_disagreeing_is_an_error():
    u = usage()
    u["prompt_cache_hit_tokens"], u["prompt_cache_miss_tokens"] = 0, 120
    with pytest.raises(ProviderError, match="disagree"):
        client(replying(body(u))).complete(MSGS, **ARGS)


def test_hit_plus_miss_must_equal_prompt():
    with pytest.raises(ProviderError, match="inconsistent"):
        client(replying(body(usage(prompt=120, hit=64, miss=50)))).complete(MSGS, **ARGS)


def test_reasoning_tokens_and_text_surfaced():
    c = client(replying(body(usage(completion=90, reasoning=80),
                             reasoning_content="thinking..."))).complete(
        MSGS, **{**ARGS, "thinking": "enabled"})
    assert c.usage.reasoning_tokens == 80
    assert c.reasoning_content == "thinking..."


def test_reasoning_larger_than_output_is_refused():
    # Would mean completion_tokens excludes reasoning, so our cost is too low.
    with pytest.raises(ProviderError, match="inconsistent"):
        client(replying(body(usage(completion=10, reasoning=80)))).complete(MSGS, **ARGS)


def test_truncation_flagged():
    c = client(replying(body(finish="length"))).complete(MSGS, **ARGS)
    assert c.truncated


# ---------------------------------------------------------------- failures

@pytest.mark.parametrize("status", [400, 401, 402, 429, 500, 503])
def test_http_errors_raise_once_no_retry(status):
    seen = []
    with pytest.raises(ProviderError, match=f"HTTP {status}"):
        client(replying({"error": {"message": "nope"}}, status=status, seen=seen)).complete(
            MSGS, **ARGS)
    assert len(seen) == 1   # exactly one attempt


def test_network_error_raises():
    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)
    with pytest.raises(ProviderError, match="ConnectTimeout"):
        client(boom).complete(MSGS, **ARGS)


def test_malformed_body_raises():
    with pytest.raises(ProviderError, match="unexpected response shape"):
        client(replying({"choices": []})).complete(MSGS, **ARGS)


def test_key_never_in_completion():
    c = client(replying(body())).complete(MSGS, **ARGS)
    assert "test-key" not in c.model_dump_json()
