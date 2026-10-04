"""Anthropic and Grok as text providers, and which provider does which task."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai import registry
from app.ai.anthropic import Anthropic
from app.ai.grok import Grok
from app.ai.openai import OpenAI
from app.ai.provider import Audio, ProviderError
from tests.domain import family, made

SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
}


def client(answer):
    return httpx.Client(transport=httpx.MockTransport(answer))


def test_anthropic_forces_one_tool_call_and_reads_its_input():
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"] = str(request.url), request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-5",
                "content": [
                    {"type": "tool_use", "name": "answer", "input": {"title": "x"}}
                ],
                "usage": {"input_tokens": 40, "output_tokens": 7},
            },
        )

    a = Anthropic("secret-key", 10, client=client(answer))
    read = a.structured("Extract", SCHEMA, "claude-sonnet-5")
    assert (read.data, read.input_tokens, read.output_tokens) == ({"title": "x"}, 40, 7)
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "secret-key"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert "secret-key" not in seen["url"]
    body = seen["body"]
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert body["tool_choice"] == {"type": "tool", "name": "answer"}
    assert body["messages"] == [{"role": "user", "content": "Extract"}]


def test_anthropic_text_joins_the_text_blocks():
    blocks = [{"type": "text", "text": "Hello "}, {"type": "text", "text": "there"}]
    reply = {
        "content": blocks,
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }
    a = Anthropic("k", 10, client=client(lambda r: httpx.Response(200, json=reply)))
    said = a.text("hi", "claude-sonnet-5")
    assert (said.text, said.model) == ("Hello there", "claude-sonnet-5")


def test_grok_asks_for_the_schema_and_parses_the_json():
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"] = str(request.url), request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "grok-4.7",
                "choices": [{"message": {"content": json.dumps({"title": "y"})}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 5},
            },
        )

    g = Grok("secret-key", 10, client=client(answer))
    read = g.structured("Extract", SCHEMA, "grok-4.7")
    assert (read.data, read.input_tokens, read.output_tokens) == ({"title": "y"}, 30, 5)
    assert seen["url"] == "https://api.x.ai/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer secret-key"
    shape = seen["body"]["response_format"]
    assert shape["type"] == "json_schema"
    assert shape["json_schema"]["schema"] == SCHEMA


@pytest.mark.parametrize("make", [Anthropic, Grok])
def test_neither_can_transcribe(make):
    with pytest.raises(ProviderError) as caught:
        make("k", 10).transcribe(Audio(b"x", "audio/mpeg"), "Transcribe", "m")
    assert not caught.value.retryable
    assert make.audio is False


ANTHROPIC_BROKE = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "Credit balance is too low."},
}
GROK_BROKE = {"code": "forbidden", "error": "Your team has no credits."}
NO_TOOL = {"content": [], "stop_reason": "max_tokens"}
NOT_JSON = {"choices": [{"message": {"content": "not json"}}]}
REFUSED = {"choices": [{"message": {"refusal": "No."}}]}


@pytest.mark.parametrize(
    "make,status,body,message,retryable",
    [
        (Anthropic, 400, ANTHROPIC_BROKE, "Anthropic answered 400: Credit balance", 0),
        (Anthropic, 529, {}, "Anthropic answered 529", 1),
        (Anthropic, 429, {}, "Anthropic answered 429: Too Many Requests", 1),
        (Anthropic, 200, NO_TOOL, "Anthropic gave no answer (max_tokens)", 1),
        (Grok, 403, GROK_BROKE, "Grok answered 403: Your team has no credits.", 0),
        (Grok, 503, {}, "Grok answered 503: Service Unavailable", 1),
        (Grok, 200, NOT_JSON, "Grok's answer was not the JSON asked for", 1),
        (Grok, 200, REFUSED, "Grok refused: No.", 0),
    ],
)
def test_failures_say_why_and_whether_to_retry(make, status, body, message, retryable):
    p = make("k", 10, client=client(lambda r: httpx.Response(status, json=body)))
    with pytest.raises(ProviderError) as caught:
        p.structured("hi", SCHEMA, "m")
    assert str(caught.value).startswith(message)
    assert caught.value.retryable == bool(retryable)


def keys(settings, **names):
    update = {f"{n}_api_key": SecretStr("k") if v else None for n, v in names.items()}
    return settings.model_copy(update=update)


def test_transcription_needs_gemini_and_text_tasks_take_the_first_key(settings):
    registry.reset()
    only_claude = keys(settings, gemini=False, anthropic=True, grok=True)
    assert registry.provider(only_claude, "transcribe") is None
    assert registry.provider(only_claude, "extract").name == "anthropic"
    assert registry.model_for(only_claude, "extract", "anthropic") == "claude-sonnet-5"
    all_three = keys(settings, gemini=True, anthropic=True, grok=True)
    assert registry.provider(all_three, "transcribe").name == "gemini"
    assert registry.provider(all_three, "questions").name == "gemini"
    none = keys(settings, gemini=False, anthropic=False, grok=False)
    assert registry.configured(none) == []
    assert registry.provider(none, "extract") is None


def test_the_owner_chooses_the_provider_for_each_text_task(settings):
    registry.reset()
    chosen = keys(settings, gemini=True, anthropic=True, grok=True).model_copy(
        update={"ai_provider": "grok", "ai_questions_provider": "Anthropic"}
    )
    assert registry.provider(chosen, "extract").name == "grok"
    assert registry.provider(chosen, "questions").name == "anthropic"
    assert registry.provider(chosen, "transcribe").name == "gemini"
    assert registry.model_for(chosen, "extract", "grok") == "grok-4.7"
    # A choice without its key falls back to the first provider that has one.
    missing = keys(settings, gemini=True, anthropic=False, grok=False).model_copy(
        update={"ai_provider": "anthropic"}
    )
    assert registry.provider(missing, "extract").name == "gemini"


def test_the_status_says_who_does_what(session, settings):
    from app.core.settings import get_settings

    registry.reset()
    chosen = keys(settings, gemini=False, anthropic=True, grok=True).model_copy(
        update={"ai_questions_provider": "grok"}
    )
    c = family(session)
    c.app.dependency_overrides[get_settings] = lambda: chosen
    shown = made(c.get("/api/ai/status"), 200)
    assert shown["tasks"] == [
        {"task": "transcribe", "provider": None, "model": None},
        {"task": "extract", "provider": "anthropic", "model": "claude-sonnet-5"},
        {"task": "questions", "provider": "grok", "model": "grok-4.7"},
    ]
    assert (shown["enabled"], shown["transcription"], shown["extraction"]) == (
        True,
        False,
        True,
    )


QUESTIONS = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {"type": "object"}},
        "note": {"type": "string"},
    },
}


@pytest.mark.parametrize(
    "sent",
    [
        # What Claude was seen sending: the whole answer, as a string, in its field.
        '{"questions": [{"text": "Which brother?"}]}',
        '[{"text": "Which brother?"}]',
        [{"text": "Which brother?"}],
    ],
)
def test_claude_lists_sent_as_strings_are_unpacked(sent):
    reply = {
        "content": [
            {"type": "tool_use", "input": {"questions": sent, "note": "[kept]"}}
        ],
        "usage": {},
    }
    a = Anthropic("k", 10, client=client(lambda r: httpx.Response(200, json=reply)))
    read = a.structured("Ask", QUESTIONS, "claude-sonnet-5")
    assert read.data == {"questions": [{"text": "Which brother?"}], "note": "[kept]"}


def test_an_unreadable_string_is_left_as_it_came():
    from app.ai.anthropic import unpack

    assert unpack({"questions": "not json"}, QUESTIONS) == {"questions": "not json"}


def test_openai_transcribes_a_named_file_with_the_prompt():
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["headers"] = str(request.url), request.headers
        seen["form"] = request.content
        return httpx.Response(
            200,
            json={
                "text": " Jim drove us to Erie. ",
                "usage": {"type": "tokens", "input_tokens": 191, "output_tokens": 38},
            },
        )

    o = OpenAI("secret-key", 10, client=client(answer))
    heard = o.transcribe(Audio(b"mp3", "audio/mpeg"), "Transcribe", "gpt-transcribe")
    assert (heard.text, heard.input_tokens, heard.output_tokens) == (
        "Jim drove us to Erie.",
        191,
        38,
    )
    assert seen["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen["headers"]["authorization"] == "Bearer secret-key"
    assert seen["headers"]["content-type"].startswith("multipart/form-data")
    form = seen["form"].decode(errors="replace")
    for part in ('filename="recording.mp3"', "gpt-transcribe", "Transcribe"):
        assert part in form
    webm = o.transcribe(Audio(b"x", "audio/webm;codecs=opus"), "T", "m")
    assert webm.text == "Jim drove us to Erie."
    assert 'filename="recording.webm"' in seen["form"].decode(errors="replace")


def test_openai_billed_by_the_second_reports_no_tokens():
    reply = {"text": "Hello.", "usage": {"type": "duration", "seconds": 3}}
    o = OpenAI("k", 10, client=client(lambda r: httpx.Response(200, json=reply)))
    heard = o.transcribe(Audio(b"x", "audio/mpeg"), "T", "gpt-transcribe")
    assert (heard.text, heard.input_tokens, heard.output_tokens) == ("Hello.", 0, 0)


def test_openai_asks_for_the_schema_without_a_temperature():
    seen = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-5.5-2026-04-23",
                "choices": [{"message": {"content": json.dumps({"title": "z"})}}],
                "usage": {"prompt_tokens": 376, "completion_tokens": 269},
            },
        )

    read = OpenAI("k", 10, client=client(answer)).structured("E", SCHEMA, "gpt-5.5")
    assert (read.data, read.model, read.input_tokens) == (
        {"title": "z"},
        "gpt-5.5-2026-04-23",
        376,
    )
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert "temperature" not in seen["body"]
    shape = seen["body"]["response_format"]["json_schema"]
    assert (shape["schema"], shape["strict"]) == (SCHEMA, False)


@pytest.mark.parametrize(
    "status,body,message,retryable",
    [
        (429, {"error": {"message": "Rate limit reached."}}, "OpenAI answered 429", 1),
        (401, {"error": {"message": "Incorrect API key."}}, "OpenAI answered 401", 0),
        (200, {"usage": {}}, "OpenAI gave no transcript", 1),
    ],
)
def test_openai_transcription_failures(status, body, message, retryable):
    o = OpenAI("k", 10, client=client(lambda r: httpx.Response(status, json=body)))
    with pytest.raises(ProviderError) as caught:
        o.transcribe(Audio(b"x", "audio/mpeg"), "T", "m")
    assert str(caught.value).startswith(message)
    assert caught.value.retryable == bool(retryable)


def test_openai_can_transcribe_when_gemini_cannot(settings):
    registry.reset()
    no_gemini = keys(settings, gemini=False, anthropic=True, grok=False, openai=True)
    assert registry.provider(no_gemini, "transcribe").name == "openai"
    assert registry.model_for(no_gemini, "transcribe", "openai") == "gpt-transcribe"
    assert registry.provider(no_gemini, "extract").name == "anthropic"
    assert registry.model_for(no_gemini, "extract", "openai") == "gpt-5.5"
    both = keys(settings, gemini=True, anthropic=False, grok=False, openai=True)
    assert registry.provider(both, "transcribe").name == "gemini"
    chosen = both.model_copy(update={"ai_transcribe_provider": "openai"})
    assert registry.provider(chosen, "transcribe").name == "openai"
    # A provider that cannot hear is never chosen to transcribe.
    deaf = keys(settings, gemini=False, anthropic=True, grok=True, openai=False)
    deaf = deaf.model_copy(update={"ai_transcribe_provider": "anthropic"})
    assert registry.provider(deaf, "transcribe") is None
