"""Tests for nlsh/backends.py, with all OpenAI API calls mocked."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from PIL import Image

from nlsh.backends import BackendManager, LLMBackend, strip_markdown_code_blocks
from nlsh.config import Config

from .conftest import make_chat_response


def _make_png_bytes(size=(20, 20), color=(0, 255, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def make_api_error(cls, message, status_code=400):
    """Construct a real openai.* exception instance (not a mock)."""
    req = httpx.Request("POST", "http://localhost:9999/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return cls(message, response=resp, body=None)


def make_tool_call(call_id, name, arguments_json):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments_json),
    )


@pytest.fixture
def backend(config):
    b = LLMBackend(config.get_backend(0))
    b.client = MagicMock()
    b.client.chat.completions.create = AsyncMock(return_value=make_chat_response("ls -la"))
    return b


@pytest.fixture
def vision_config(tmp_path):
    cfg = tmp_path / "vision_config.yml"
    cfg.write_text(
        "shell: bash\n"
        "backends:\n"
        "  - name: plain-backend\n"
        "    url: http://localhost:9999/v1\n"
        "    api_key: dummy-key\n"
        "    model: plain-model\n"
        "  - name: vision-backend\n"
        "    url: http://localhost:9999/v1\n"
        "    api_key: dummy-key\n"
        "    model: vision-model\n"
        "    supports_vision: true\n"
        "default_backend: 0\n"
    )
    return Config(str(cfg))


@pytest.fixture
def vision_backend(vision_config):
    b = LLMBackend(vision_config.get_backend(1))
    b.client = MagicMock()
    b.client.chat.completions.create = AsyncMock(return_value=make_chat_response("some analysis"))
    return b


class TestStripMarkdownCodeBlocks:
    def test_fenced_with_language(self):
        assert strip_markdown_code_blocks("```bash\nls -la\n```") == "ls -la"

    def test_fenced_without_language(self):
        assert strip_markdown_code_blocks("```\nls -la\n```") == "ls -la"

    def test_single_backticks(self):
        assert strip_markdown_code_blocks("`ls -la`") == "ls -la"

    def test_plain_text_unchanged(self):
        assert strip_markdown_code_blocks("ls -la") == "ls -la"

    def test_multiline_fenced_content(self):
        text = "```bash\nfind . -name '*.py' \\\n  | xargs wc -l\n```"
        result = strip_markdown_code_blocks(text)
        assert result == "find . -name '*.py' \\\n  | xargs wc -l"


class TestCalculateTemperature:
    def test_no_regeneration(self, backend):
        assert backend._calculate_temperature(0) == pytest.approx(0.2)

    def test_some_regeneration(self, backend):
        assert backend._calculate_temperature(3) == pytest.approx(0.5)

    def test_capped_at_one(self, backend):
        assert backend._calculate_temperature(20) == pytest.approx(1.0)


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_returns_content_and_strips_markdown_by_default(self, backend):
        backend.client.chat.completions.create = AsyncMock(
            return_value=make_chat_response("```bash\nls -la\n```")
        )
        result = await backend.generate_response("list files", "system context")
        assert result == "ls -la"

    @pytest.mark.asyncio
    async def test_keeps_markdown_when_disabled(self, backend):
        backend.client.chat.completions.create = AsyncMock(
            return_value=make_chat_response("```bash\nls -la\n```")
        )
        result = await backend.generate_response(
            "list files", "system context", strip_markdown=False
        )
        assert result == "```bash\nls -la\n```"

    @pytest.mark.asyncio
    async def test_none_content_returns_error_not_attribute_error(self, backend):
        """`message.content` is Optional in the API schema.

        Regression test: the code called .strip() on it unconditionally, which
        raised AttributeError when a backend returned a null content (e.g. a
        tool-call-only or filtered response).
        """
        backend.client.chat.completions.create = AsyncMock(return_value=make_chat_response(None))
        result = await backend.generate_response("list files", "system context")
        assert result == "Error: No response generated"

    @pytest.mark.asyncio
    async def test_create_called_with_expected_kwargs(self, backend):
        await backend.generate_response(
            "list files", "system context", max_tokens=123, regeneration_count=2
        )
        call = backend.client.chat.completions.create.call_args
        assert call.kwargs["model"] == backend.model
        assert call.kwargs["temperature"] == pytest.approx(0.4)
        assert call.kwargs["max_tokens"] == 123
        assert "response_format" not in call.kwargs

    @pytest.mark.asyncio
    async def test_image_on_non_vision_backend_raises_value_error(self, backend):
        with pytest.raises(ValueError, match="does not support vision"):
            await backend.generate_response(
                "describe image",
                "system context",
                image_data=_make_png_bytes(),
                image_mime_type="image/png",
            )

    @pytest.mark.asyncio
    async def test_vision_path_sends_image_url_part(self, vision_backend):
        await vision_backend.generate_response(
            "describe image",
            "system context",
            image_data=_make_png_bytes(),
            image_mime_type="image/png",
        )
        call = vision_backend.client.chat.completions.create.call_args
        user_message = call.kwargs["messages"][1]
        assert isinstance(user_message["content"], list)
        image_parts = [p for p in user_message["content"] if p["type"] == "image_url"]
        assert len(image_parts) == 1
        assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


class TestGenerateStructuredCommand:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("danger", ["safe", "caution", "destructive"])
    async def test_valid_json_response(self, backend, danger):
        raw = f'{{"command": "ls -la", "danger_level": "{danger}"}}'
        backend.client.chat.completions.create = AsyncMock(return_value=make_chat_response(raw))
        result = await backend.generate_structured_command("list files", "system context")
        assert result.command == "ls -la"
        assert result.danger_level == danger

    @pytest.mark.asyncio
    async def test_garbage_response_falls_back_to_stripped_text(self, backend):
        backend.client.chat.completions.create = AsyncMock(
            return_value=make_chat_response("```bash\nls -la\n```")
        )
        result = await backend.generate_structured_command("list files", "system context")
        assert result.command == "ls -la"
        assert result.danger_level is None

    @pytest.mark.asyncio
    async def test_rejection_falls_back_from_json_schema_to_json_object(self, backend):
        error = make_api_error(openai.BadRequestError, "invalid response_format: json_schema")
        success = make_chat_response('{"command": "df -h", "danger_level": "safe"}')
        backend.client.chat.completions.create = AsyncMock(side_effect=[error, success])

        result = await backend.generate_structured_command("check disk", "system context")

        assert result.command == "df -h"
        assert result.danger_level == "safe"
        assert backend._resolved_structured_mode == "json_object"
        assert backend.client.chat.completions.create.call_count == 2
        first_call, second_call = backend.client.chat.completions.create.call_args_list
        assert first_call.kwargs["response_format"]["type"] == "json_schema"
        assert second_call.kwargs["response_format"]["type"] == "json_object"

    @pytest.mark.asyncio
    async def test_structured_output_off_omits_response_format(self, backend):
        backend.structured_output = "off"
        backend.client.chat.completions.create = AsyncMock(
            return_value=make_chat_response("ls -la")
        )
        result = await backend.generate_structured_command("list files", "system context")
        assert result.command == "ls -la"
        call = backend.client.chat.completions.create.call_args
        assert "response_format" not in call.kwargs


class TestGenerateCommandWithTools:
    @pytest.fixture
    def registry(self):
        reg = MagicMock()
        reg.definitions.return_value = [
            {"type": "function", "function": {"name": "list_directory"}}
        ]
        reg.execute.return_value = "file1.txt\nfile2.txt"
        return reg

    @pytest.mark.asyncio
    async def test_tool_call_round_trip(self, backend, registry):
        tool_call = make_tool_call("call_1", "list_directory", '{"path": "."}')
        first_response = make_chat_response(None, tool_calls=[tool_call])
        second_response = make_chat_response('{"command": "cat file1.txt", "danger_level": "safe"}')
        backend.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, second_response]
        )

        result = await backend.generate_command_with_tools(
            "show me a file", "system context", registry
        )

        registry.execute.assert_called_once_with("list_directory", '{"path": "."}')
        assert result.command == "cat file1.txt"
        assert result.danger_level == "safe"
        assert result.tool_calls == [
            {
                "name": "list_directory",
                "arguments": '{"path": "."}',
                "result_chars": len("file1.txt\nfile2.txt"),
            }
        ]

        second_call = backend.client.chat.completions.create.call_args_list[1]
        messages = second_call.kwargs["messages"]
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call_1"
        assert tool_messages[0]["content"] == "file1.txt\nfile2.txt"

    @pytest.mark.asyncio
    async def test_round_limit_forces_final_answer_without_tools(self, backend, registry):
        from nlsh.backends import MAX_TOOL_ROUNDS

        tool_call = make_tool_call("call_x", "list_directory", "{}")
        tool_round_response = make_chat_response(None, tool_calls=[tool_call])
        final_response = make_chat_response('{"command": "echo done", "danger_level": "safe"}')

        responses = [tool_round_response] * MAX_TOOL_ROUNDS + [final_response]
        backend.client.chat.completions.create = AsyncMock(side_effect=responses)

        result = await backend.generate_command_with_tools(
            "keep exploring", "system context", registry
        )

        assert result.command == "echo done"
        assert backend.client.chat.completions.create.call_count == MAX_TOOL_ROUNDS + 1
        last_call = backend.client.chat.completions.create.call_args_list[-1]
        assert "tools" not in last_call.kwargs

    @pytest.mark.asyncio
    async def test_tools_rejected_falls_back_to_structured(self, backend, registry):
        error = make_api_error(openai.BadRequestError, "tools is not supported for this model")
        success = make_chat_response('{"command": "ls", "danger_level": "safe"}')
        backend.client.chat.completions.create = AsyncMock(side_effect=[error, success])

        result = await backend.generate_command_with_tools("list files", "system context", registry)

        assert result.command == "ls"
        assert backend._tools_supported is False
        registry.execute.assert_not_called()


class TestLLMBackendInit:
    def test_local_url_with_dummy_key_succeeds(self):
        b = LLMBackend(
            {
                "name": "local",
                "url": "http://localhost:9999/v1",
                "api_key": "dummy-key",
                "model": "m",
            }
        )
        assert b.timeout == pytest.approx(300.0)

    def test_non_local_short_api_key_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid API key configuration"):
            LLMBackend(
                {
                    "name": "remote",
                    "url": "https://api.example.com/v1",
                    "api_key": "short",
                    "model": "m",
                }
            )

    def test_non_local_valid_api_key_succeeds(self):
        b = LLMBackend(
            {
                "name": "remote",
                "url": "https://api.example.com/v1",
                "api_key": "a-long-enough-key",
                "model": "m",
            }
        )
        assert b.api_key == "a-long-enough-key"

    def test_reasoning_model_autodetected_from_name(self):
        b = LLMBackend(
            {
                "name": "my-reasoning-model",
                "url": "http://localhost:9999/v1",
                "api_key": "dummy-key",
                "model": "m",
            }
        )
        assert b.is_reasoning_model is True

    def test_client_init_failure_wrapped_in_value_error(self, monkeypatch):
        def raise_error(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("nlsh.backends.openai.AsyncOpenAI", raise_error)
        with pytest.raises(ValueError, match="Failed to initialize backend"):
            LLMBackend(
                {
                    "name": "local",
                    "url": "http://localhost:9999/v1",
                    "api_key": "dummy-key",
                    "model": "m",
                }
            )


class TestGenerateResponseAuthenticationError:
    @pytest.mark.asyncio
    async def test_api_key_related_message(self, backend):
        error = make_api_error(openai.AuthenticationError, "Incorrect API key provided", 401)
        backend.client.chat.completions.create = AsyncMock(side_effect=error)
        with pytest.raises(ValueError, match="check your API key configuration"):
            await backend.generate_response("list files", "system context")

    @pytest.mark.asyncio
    async def test_other_auth_error_message(self, backend):
        error = make_api_error(openai.AuthenticationError, "account suspended", 401)
        backend.client.chat.completions.create = AsyncMock(side_effect=error)
        with pytest.raises(ValueError, match="account suspended"):
            await backend.generate_response("list files", "system context")


class TestGenerateResponseStreaming:
    @pytest.mark.asyncio
    async def test_streaming_accumulates_content_and_strips_markdown(self, backend, capsys):
        chunk1 = SimpleNamespace(
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content="```bash\n", reasoning_content=None))
            ]
        )
        chunk2 = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="ls -la\n```", reasoning_content=None)
                )
            ]
        )

        class FakeStream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                for chunk in (chunk1, chunk2):
                    yield chunk

        backend.client.chat.completions.create = AsyncMock(return_value=FakeStream())

        result = await backend.generate_response("list files", "system context", verbose=True)
        assert result == "ls -la"


class TestGenerateCommandWithToolsHardFailure:
    @pytest.mark.asyncio
    async def test_tool_calling_on_hard_failure_raises(self, backend):
        backend.tool_calling = "on"
        registry = MagicMock()
        registry.definitions.return_value = [
            {"type": "function", "function": {"name": "list_directory"}}
        ]
        error = make_api_error(openai.BadRequestError, "tools is not supported for this model")
        backend.client.chat.completions.create = AsyncMock(side_effect=error)

        with pytest.raises(ValueError, match="rejected the 'tools' parameter"):
            await backend.generate_command_with_tools("list files", "system context", registry)


class TestBackendManager:
    def test_get_backend_caches_instance(self, config):
        manager = BackendManager(config)
        b1 = manager.get_backend(0)
        b2 = manager.get_backend(0)
        assert b1 is b2

    def test_get_vision_capable_backend_finds_vision_backend(self, vision_config):
        manager = BackendManager(vision_config)
        b = manager.get_vision_capable_backend()
        assert b.name == "vision-backend"

    def test_get_vision_capable_backend_prefers_preferred_index(self, vision_config):
        manager = BackendManager(vision_config)
        b = manager.get_vision_capable_backend(preferred_index=1)
        assert b.name == "vision-backend"

    def test_get_vision_capable_backend_raises_when_none(self, config):
        manager = BackendManager(config)
        with pytest.raises(ValueError, match="No vision-capable backend found"):
            manager.get_vision_capable_backend()
