"""
LLM backend handling for nlsh.

This module provides functionality for interacting with different LLM backends.
"""

import re
import sys
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import openai

from nlsh.image_utils import prepare_image_for_api
from nlsh.structured import (
    JSON_OBJECT_INSTRUCTION,
    build_response_format,
    parse_command_response,
)

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from nlsh.config import Config


def strip_markdown_code_blocks(text: str) -> str:
    """Strip Markdown code blocks from text.

    This function removes Markdown code block formatting from the text.
    It handles three types of code blocks:
    1. Multiline code blocks with language info: ```language\ncode\n```
    2. Multiline code blocks without language info: ```\ncode\n```
    3. Single line code blocks: `code`

    Args:
        text: Text that may contain Markdown code blocks.

    Returns:
        str: Text with code blocks stripped of their Markdown formatting.
    """
    # Handle multiline code blocks with or without language info
    # Pattern: ```[language]\ncode\n```
    pattern = r"```(?:[a-zA-Z0-9_+-]+)?\n?(.*?)\n?```"
    result = re.sub(pattern, r"\1", text, flags=re.DOTALL)

    # Handle the case where the entire response is enclosed in single backticks
    # Pattern: `code`
    stripped_result = result.strip()
    if stripped_result.startswith("`") and stripped_result.endswith("`"):
        result = stripped_result[1:-1]

    return result.strip()


# Maximum number of tool-call round trips per generation before a final
# answer is forced.
MAX_TOOL_ROUNDS = 5


class _ToolsRejected(Exception):
    """Raised internally when a backend appears to reject the `tools`
    (function calling) parameter. Caught by `generate_command_with_tools`,
    which decides whether to raise a user-facing error (`tool_calling: on`)
    or fall back silently (`tool_calling: auto`)."""


@dataclass
class CommandResult:
    """Result of a (possibly structured) command generation call.

    Attributes:
        command: The generated shell command.
        danger_level: Model-reported danger level ("safe", "caution",
            "destructive"), or None if unknown/unavailable (e.g. legacy
            plain-text path, or a response that could not be parsed as
            structured JSON).
        raw_response: The raw model response as it came from the API (JSON or
            plain text), before any parsing/stripping. Useful for logging.
        tool_calls: Optional list of `{"name", "arguments", "result_chars"}`
            summaries of local tool invocations made while generating this
            result. None when tool calling was not used. Full tool
            results are intentionally not stored here (they can be large) --
            only lengths, for logging purposes.
    """

    command: str
    danger_level: Optional[str] = None
    raw_response: str = ""
    tool_calls: Optional[list] = None


class LLMBackend:
    """Base class for LLM backends."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the backend.

        Args:
            config: Backend configuration.
        """
        self.config = config
        self.name = config.get("name", "unknown")
        self.url = config.get("url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.is_reasoning_model = config.get("is_reasoning_model", False)
        self.timeout = float(config.get("timeout", 120.0))

        # Structured output configuration. "auto" (default) tries
        # json_schema, then json_object, then falls back to legacy plain
        # text; the resolved working mode is cached for the lifetime of this
        # backend instance so we don't retry a known-unsupported mode on
        # every call (see generate_structured_command below).
        self.structured_output = config.get("structured_output", "auto")
        self._resolved_structured_mode: Optional[str] = None

        # Tool calling configuration. "auto" (default) sends the
        # `tools` parameter on the first request; if the backend rejects it,
        # the result is cached on this instance for the rest of the process
        # (see generate_command_with_tools below). None = not yet determined.
        self.tool_calling = config.get("tool_calling", "auto")
        self._tools_supported: Optional[bool] = None

        # Auto-detect reasoning models by name if not explicitly set
        if not self.is_reasoning_model and "reason" in self.name.lower():
            self.is_reasoning_model = True

        # Handle API key for different types of backends
        api_key = self.api_key

        # Enhanced local backend detection
        is_local = (
            "localhost" in self.url
            or "127.0.0.1" in self.url
            or "::1" in self.url
            or self.url.startswith("unix://")
        )

        # For local models, increase timeout
        if is_local:
            self.timeout = float(config.get("timeout", 300.0))  # 5 minutes for local models

        # Check if this is a dummy key for local models
        is_dummy_key = api_key and (api_key.startswith("dummy") or api_key == "ollama")

        # Validate API key for non-local endpoints
        if not is_local and not is_dummy_key:  # noqa: SIM102
            if not self.api_key or len(self.api_key.strip()) < 8:
                raise ValueError(f"Invalid API key configuration for backend {self.name}")

        # Configure OpenAI client
        try:
            if is_local:
                # For local endpoints, don't send any auth headers
                self.client = openai.AsyncOpenAI(
                    base_url=self.url,
                    api_key="dummy-key",
                    timeout=self.timeout,
                    default_headers={"Content-Type": "application/json"},
                )

                # Ensure both sync and async clients have no auth headers
                for client_attr in ["_client", "_async_client"]:
                    if hasattr(self.client, client_attr):
                        client = getattr(self.client, client_attr)
                        if hasattr(client, "headers"):
                            client.headers.clear()
                            client.headers["Content-Type"] = "application/json"
            else:
                self.client = openai.AsyncOpenAI(
                    base_url=self.url, api_key=self.api_key, timeout=self.timeout
                )
        except Exception as e:
            raise ValueError(f"Failed to initialize backend {self.name}: {str(e)}")  # noqa: B904

    @property
    def tools_supported(self) -> Optional[bool]:
        """Whether this backend is known to support the `tools` (function
        calling) parameter.

        None means unknown/not yet attempted (only meaningful in "auto"
        mode). True/False are cached for the lifetime of this backend
        instance after the first tool-calling attempt.
        """
        return self._tools_supported

    async def _generate_streaming_response(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        strip_markdown: bool,
    ) -> str:
        """Generate a response using streaming mode.

        Args:
            messages: List of message dictionaries.
            temperature: Temperature for generation.
            max_tokens: Maximum tokens to generate.
            strip_markdown: Whether to strip markdown code blocks.

        Returns:
            str: Generated response.
        """
        full_response = ""
        sys.stderr.write("Reasoning: ")

        # Call the API with streaming.
        # `messages` is built as plain dicts rather than the SDK's
        # ChatCompletion*Param TypedDicts (they are not expressible for the
        # dynamic system/user/tool mix used here), so the argument type and the
        # stream=True overload are both narrowed by hand.
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
            stream=True,
        )

        # Process the stream
        async for chunk in stream:  # type: ignore[union-attr]
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta

                # Handle reasoning content
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    sys.stderr.write(delta.reasoning_content)
                    sys.stderr.flush()

                # Handle regular content
                if hasattr(delta, "content") and delta.content:
                    if not self.is_reasoning_model:
                        sys.stderr.write(delta.content)
                        sys.stderr.flush()
                    full_response += delta.content

        sys.stderr.write("\n")

        # Process the response
        response_text = full_response.strip()
        if strip_markdown:
            response_text = strip_markdown_code_blocks(response_text)

        return response_text

    async def _generate_non_streaming_response(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        strip_markdown: bool,
    ) -> str:
        """Generate a response without streaming.

        Args:
            messages: List of message dictionaries.
            temperature: Temperature for generation.
            max_tokens: Maximum tokens to generate.
            strip_markdown: Whether to strip markdown code blocks.

        Returns:
            str: Generated response.
        """
        # Call the API without streaming (see the note in
        # _generate_streaming_response about the plain-dict `messages` type).
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
        )

        # Extract and process the content. `content` is Optional in the API
        # schema (e.g. when a model returns only tool calls or is filtered),
        # so guard against None instead of calling .strip() on it directly.
        if response.choices and len(response.choices) > 0:
            raw_content = response.choices[0].message.content
            if raw_content is None:
                return "Error: No response generated"
            content = raw_content.strip()

            if strip_markdown:
                return strip_markdown_code_blocks(content)

            return content

        return "Error: No response generated"

    async def generate_response(
        self,
        prompt: str,
        system_context: str,
        verbose: bool = False,
        strip_markdown: bool = True,
        max_tokens: int = 500,
        regeneration_count: int = 0,
        image_data: Optional[bytes] = None,
        image_mime_type: Optional[str] = None,
    ) -> str:
        """Generate a response from the LLM based on the prompt and context.

        Args:
            prompt: User prompt.
            system_context: System context information.
            verbose: Whether to print reasoning tokens to stderr.
            strip_markdown: Whether to strip markdown code blocks from the response.
            max_tokens: Maximum tokens to generate.
            regeneration_count: Number of times the response has been regenerated.
            image_data: Optional image data for vision models.
            image_mime_type: MIME type of the image data.

        Returns:
            str: Generated response.
        """
        try:
            # Create messages for the chat completion. Values are Any because
            # a vision user message carries a list of content parts, not a str.
            messages: list[dict[str, Any]] = [{"role": "system", "content": system_context}]

            # Handle image input for vision models
            if image_data and image_mime_type:
                if not self.supports_vision():
                    raise ValueError(
                        f"Backend {self.name} does not support vision/image processing"
                    )

                # Prepare image for API
                base64_image, mime_type = prepare_image_for_api(image_data, image_mime_type)

                # Create user message with image
                user_message: dict[str, Any] = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                        },
                    ],
                }
            else:
                # Text-only message
                user_message = {"role": "user", "content": prompt}

            messages.append(user_message)

            # Calculate temperature based on regeneration count
            temperature = self._calculate_temperature(regeneration_count)

            # Generate response with or without streaming
            if verbose:
                return await self._generate_streaming_response(
                    messages, temperature, max_tokens, strip_markdown
                )
            else:
                return await self._generate_non_streaming_response(
                    messages, temperature, max_tokens, strip_markdown
                )

        except openai.AuthenticationError as e:
            error_msg = str(e)
            if "api key" in error_msg.lower():
                raise ValueError(  # noqa: B904
                    f"Authentication failed for backend {self.name}. Please check your API key configuration."
                )
            raise ValueError(  # noqa: B904
                f"Authentication failed for backend {self.name}: {error_msg}"
            )
        except Exception as e:
            print(f"Error generating command: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise

    async def _try_structured_mode(
        self,
        mode: str,
        prompt: str,
        system_context: str,
        max_tokens: int,
        regeneration_count: int,
    ) -> Optional["CommandResult"]:
        """Attempt a single structured-output generation call.

        Args:
            mode: Structured output mode to attempt ("json_schema" or "json_object").
            prompt: User prompt.
            system_context: System prompt for the structured attempt (the
                JSON-variant prompt when available). For json_object mode,
                the JSON schema instruction is appended internally.
            max_tokens: Maximum tokens to generate.
            regeneration_count: Number of times the response has been regenerated.

        Returns:
            Optional[CommandResult]: The parsed result on success (including
                the case where the content wasn't valid JSON and was treated
                as a plain-text command instead), or None if the backend
                rejected the response_format parameter (signaling the caller
                should fall back to a different mode).
        """
        system_content = system_context
        if mode == "json_object":
            # json_object mode has no server-side schema enforcement and the
            # OpenAI API requires the word "JSON" to appear in the messages.
            system_content += JSON_OBJECT_INSTRUCTION

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        temperature = self._calculate_temperature(regeneration_count)
        response_format = build_response_format(mode)

        try:
            # Plain-dict messages + an optional response_format dict (see the
            # note in _generate_streaming_response) do not match any of the
            # SDK's create() overloads, so the whole call is narrowed by hand.
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                n=1,
                response_format=response_format,
            )
        except (openai.BadRequestError, openai.UnprocessableEntityError, TypeError):
            # Backend doesn't support this structured output mode.
            return None
        except Exception as e:
            if "response_format" in str(e):
                return None
            raise

        if not response.choices:
            return None

        content = response.choices[0].message.content
        if content is None:
            return None
        content = content.strip()

        command, danger = parse_command_response(content)
        if command is None:
            # Not valid JSON matching the schema -- treat the raw content as
            # a plain-text command via the legacy stripping path. This is
            # still a "successful" attempt of this mode (not a rejection),
            # so the caller may cache this mode as the resolved one.
            return CommandResult(
                command=strip_markdown_code_blocks(content),
                danger_level=None,
                raw_response=content,
            )

        return CommandResult(command=command, danger_level=danger, raw_response=content)

    async def generate_structured_command(
        self,
        prompt: str,
        system_context: str,
        verbose: bool = False,
        max_tokens: int = 500,
        regeneration_count: int = 0,
        structured_system_context: Optional[str] = None,
    ) -> "CommandResult":
        """Generate a shell command, preferring structured JSON output.

        This method is intended for command generation/regeneration/fixing
        only (not explanations, STDIN processing, or nlgc). It does not
        change the behavior or signature of `generate_response`, which
        remains the plain-text path used elsewhere.

        Verbose (-v/-vv) requests always use the legacy plain-text path: the
        reasoning-token streaming UX is preserved as-is rather than
        replicating it for structured output, per the simplified design.
        Structured output therefore only applies to non-verbose requests.

        Args:
            prompt: User prompt.
            system_context: Plain-text system prompt (the same prompt that
                would be passed to `generate_response`). Used for the legacy
                plain-text path and any fallback to it.
            verbose: Whether to print reasoning tokens to stderr. When True,
                this always uses the legacy text path (see above).
            max_tokens: Maximum tokens to generate.
            regeneration_count: Number of times the response has been regenerated.
            structured_system_context: JSON-variant system prompt used for
                structured attempts (see PromptBuilder's `structured=True`
                prompt variants). If not provided, `system_context` is used
                for structured attempts as well.

        Returns:
            CommandResult: The generated command and, when available, the
                model-reported danger level.
        """

        async def _legacy() -> "CommandResult":
            response = await self.generate_response(
                prompt,
                system_context,
                verbose=verbose,
                strip_markdown=True,
                max_tokens=max_tokens,
                regeneration_count=regeneration_count,
            )
            return CommandResult(command=response, danger_level=None, raw_response=response)

        # System prompt for structured attempts: the JSON-variant prompt if
        # provided, otherwise the plain one.
        structured_context = structured_system_context or system_context

        if verbose or self.structured_output == "off":
            return await _legacy()

        # Determine effective mode: explicit config wins; "auto" uses the
        # cached resolved mode if we've already determined one for this
        # backend instance, otherwise starts with json_schema.
        if self.structured_output in ("json_schema", "json_object"):
            mode = self.structured_output
        else:
            mode = self._resolved_structured_mode or "json_schema"

        if mode == "off":
            # "auto" previously resolved to "off" for this backend instance.
            return await _legacy()

        result = await self._try_structured_mode(
            mode, prompt, structured_context, max_tokens, regeneration_count
        )
        if result is not None:
            if self.structured_output == "auto":
                self._resolved_structured_mode = mode
            return result

        # The attempted mode was rejected by the backend.
        if self.structured_output == "auto" and mode == "json_schema":
            result = await self._try_structured_mode(
                "json_object", prompt, structured_context, max_tokens, regeneration_count
            )
            if result is not None:
                self._resolved_structured_mode = "json_object"
                return result

        # All structured attempts failed -- fall back to legacy plain text.
        if self.structured_output == "auto":
            self._resolved_structured_mode = "off"

        return await _legacy()

    def _next_structured_mode(self, mode: str) -> str:
        """Return the next structured-output mode to try after `mode` was
        rejected by the backend.

        Follows the same fallback chain as `generate_structured_command`:
        json_schema -> json_object -> off in "auto" mode; any explicitly
        configured mode degrades straight to "off" (no further structured
        attempts).
        """
        if mode == "json_schema" and self.structured_output == "auto":
            return "json_object"
        return "off"

    async def _tool_round_call(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tools_defs: Optional[list[dict]],
        mode: str,
        system_content_for,
    ) -> tuple[Any, str]:
        """Perform one non-streaming chat completion call for the tool-calling
        loop.

        Combines `tools` (function calling) with `response_format`
        (structured output). The two features have independent fallback
        chains: if the backend rejects `response_format` for the current
        mode, this downgrades the mode (json_schema -> json_object -> off)
        and retries while keeping `tools` present. If the backend instead
        appears to reject `tools` itself (or the rejection is ambiguous),
        this raises `_ToolsRejected` so the caller can fall back to the
        tools-less path.

        Args:
            messages: Conversation so far (mutated in place: `messages[0]`,
                the system message, is rewritten if the mode downgrades).
            temperature: Temperature for generation.
            max_tokens: Maximum tokens to generate.
            tools_defs: OpenAI `tools` parameter value, or falsy to omit it
                entirely (used for the final forced-answer call).
            mode: Structured output mode to attempt first.
            system_content_for: Callable mapping a mode to the system prompt
                content that should be used for it.

        Returns:
            (response, resolved_mode): the API response and the structured
            output mode that was actually used for it.
        """
        current_mode = mode
        downgrades = 0
        while True:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "n": 1,
            }
            if tools_defs:
                kwargs["tools"] = tools_defs
            response_format = build_response_format(current_mode) if current_mode != "off" else None
            if response_format is not None:
                kwargs["response_format"] = response_format

            try:
                response = await self.client.chat.completions.create(**kwargs)
                return response, current_mode
            except (openai.BadRequestError, openai.UnprocessableEntityError, TypeError) as e:
                msg = str(e).lower()
                tools_issue = bool(tools_defs) and ("tool" in msg or "function" in msg)
                format_issue = current_mode != "off" and (
                    "response_format" in msg
                    or "response format" in msg
                    or "json_schema" in msg
                    or "json schema" in msg
                )
                if format_issue and not tools_issue and downgrades < 2:
                    current_mode = self._next_structured_mode(current_mode)
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] = system_content_for(current_mode)
                    downgrades += 1
                    continue
                if tools_defs:
                    raise _ToolsRejected(str(e)) from e
                raise
            except Exception as e:
                msg = str(e).lower()
                if tools_defs and ("tool" in msg or "function" in msg):
                    raise _ToolsRejected(str(e)) from e
                if current_mode != "off" and "response_format" in msg and downgrades < 2:
                    current_mode = self._next_structured_mode(current_mode)
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] = system_content_for(current_mode)
                    downgrades += 1
                    continue
                raise

    async def _handle_tools_rejected(
        self,
        prompt: str,
        system_context: str,
        structured_system_context: Optional[str],
        verbose: bool,
        max_tokens: int,
        regeneration_count: int,
        error_message: str = "",
    ) -> "CommandResult":
        """Handle a backend's rejection of the `tools` parameter.

        In "auto" mode, this caches the backend as not supporting tool
        calling (for the remainder of the process) and falls back to the
        structured-output path for this request. In "on" mode, this is a
        hard configuration error -- the user must explicitly disable tool
        calling for this backend.
        """
        if self.tool_calling == "on":
            suffix = f" ({error_message})" if error_message else ""
            raise ValueError(
                f"Backend {self.name} rejected the 'tools' parameter required for "
                "function calling. Set 'tool_calling: off' for this backend in your "
                f"config to disable tool calling.{suffix}"
            )

        self._tools_supported = False
        return await self.generate_structured_command(
            prompt,
            system_context,
            verbose=verbose,
            max_tokens=max_tokens,
            regeneration_count=regeneration_count,
            structured_system_context=structured_system_context,
        )

    async def generate_command_with_tools(
        self,
        prompt: str,
        system_context: str,
        registry,
        verbose: bool = False,
        max_tokens: int = 500,
        regeneration_count: int = 0,
        structured_system_context: Optional[str] = None,
    ) -> "CommandResult":
        """Generate a shell command, allowing the model to call local
        read-only tools (via OpenAI function calling) to fetch context on
        demand instead of relying solely on up-front prompt context.

        This method is intended for command generation/regeneration/fixing
        only (not explanations, STDIN processing, or nlgc), matching the
        scope of `generate_structured_command`.

        Verbose (-v/-vv) requests always use the legacy plain-text/streaming
        path (delegated to `generate_structured_command`, which itself
        delegates to the plain-text path for verbose requests): the
        reasoning-token streaming UX is preserved as-is, and tool calling
        runs in non-streaming mode only.

        Args:
            prompt: User prompt.
            system_context: Plain-text system prompt (used for the legacy
                path and as a fallback system prompt for "off" mode).
            registry: A `LocalToolRegistry`-like object exposing
                `definitions() -> list[dict]` and
                `execute(name, arguments_json) -> str`.
            verbose: Whether to print reasoning tokens to stderr. When True,
                this always delegates to the legacy text path (see above).
            max_tokens: Maximum tokens to generate.
            regeneration_count: Number of times the response has been regenerated.
            structured_system_context: JSON-variant system prompt used for
                structured attempts. If not provided, `system_context` is
                used for structured attempts as well.

        Returns:
            CommandResult: The generated command, the model-reported danger
            level (when available), and a summary of any tool calls made.
        """
        # Tool calling only applies to non-verbose, non-streaming requests.
        # Verbose requests keep the legacy streaming path (with reasoning
        # display) exactly as generate_structured_command already does.
        if verbose or self.tool_calling == "off" or self._tools_supported is False:
            return await self.generate_structured_command(
                prompt,
                system_context,
                verbose=verbose,
                max_tokens=max_tokens,
                regeneration_count=regeneration_count,
                structured_system_context=structured_system_context,
            )

        structured_context = structured_system_context or system_context

        def _system_content_for(mode: str) -> str:
            if mode == "off":
                return system_context
            content = structured_context
            if mode == "json_object":
                content += JSON_OBJECT_INSTRUCTION
            return content

        if self.structured_output == "off":
            mode = "off"
        elif self.structured_output in ("json_schema", "json_object"):
            mode = self.structured_output
        else:
            mode = self._resolved_structured_mode or "json_schema"

        temperature = self._calculate_temperature(regeneration_count)
        tools_defs = registry.definitions()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _system_content_for(mode)},
            {"role": "user", "content": prompt},
        ]
        tool_calls_log: list[dict[str, Any]] = []

        def _parse(content: Optional[str]) -> "CommandResult":
            text = (content or "").strip()
            if mode != "off":
                command, danger = parse_command_response(text)
                if command is not None:
                    return CommandResult(
                        command=command,
                        danger_level=danger,
                        raw_response=text,
                        tool_calls=tool_calls_log,
                    )
            return CommandResult(
                command=strip_markdown_code_blocks(text),
                danger_level=None,
                raw_response=text,
                tool_calls=tool_calls_log,
            )

        for _round in range(MAX_TOOL_ROUNDS):
            try:
                response, mode = await self._tool_round_call(
                    messages, temperature, max_tokens, tools_defs, mode, _system_content_for
                )
            except _ToolsRejected as e:
                return await self._handle_tools_rejected(
                    prompt,
                    system_context,
                    structured_system_context,
                    verbose,
                    max_tokens,
                    regeneration_count,
                    str(e),
                )

            if self._tools_supported is None:
                self._tools_supported = True
            if self.structured_output == "auto":
                self._resolved_structured_mode = mode

            if not response.choices:
                break

            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None)

            if tool_calls:
                # The assistant message carrying tool_calls MUST be appended
                # before the corresponding tool result messages, and each
                # tool result MUST carry the matching tool_call_id.
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )
                for tc in tool_calls:
                    # tc.function.arguments is a JSON string, not a dict --
                    # pass it through untouched to the registry.
                    result = registry.execute(tc.function.name, tc.function.arguments)
                    tool_calls_log.append(
                        {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                            "result_chars": len(result),
                        }
                    )
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue

            return _parse(message.content)

        # Round cap reached (or an empty-choices response slipped through):
        # force a final answer without tools.
        response = None
        try:
            response, mode = await self._tool_round_call(
                messages, temperature, max_tokens, None, mode, _system_content_for
            )
        except _ToolsRejected:
            response = None

        if response is not None and response.choices:
            return _parse(response.choices[0].message.content)

        # Still nothing usable -- fall back entirely rather than returning
        # an empty command.
        return await self.generate_structured_command(
            prompt,
            system_context,
            verbose=verbose,
            max_tokens=max_tokens,
            regeneration_count=regeneration_count,
            structured_system_context=structured_system_context,
        )

    def _calculate_temperature(self, regeneration_count: int) -> float:
        # Calculate temperature based on regeneration count (0.2 base, +0.1 per regeneration, max 1.0)
        return min(0.2 + (regeneration_count * 0.1), 1.0)

    def supports_vision(self) -> bool:
        """Check if this backend supports vision/image processing.

        Returns:
            bool: True if backend supports vision.
        """
        return bool(self.config.get("supports_vision", False))


class BackendManager:
    """Manager for LLM backends."""

    def __init__(self, config: "Config"):
        """Initialize the backend manager.

        Args:
            config: Configuration object.
        """
        self.config = config
        # Keyed by f"{backend_name}_{index}" (see get_backend).
        self.backends: dict[str, LLMBackend] = {}

    def get_backend(self, index: Optional[int] = None) -> LLMBackend:
        """Get a backend instance.

        Args:
            index: Optional backend index. If not provided, uses default_backend.

        Returns:
            LLMBackend: Backend instance.
        """
        # Get backend configuration
        backend_config = self.config.get_backend(index)
        if not backend_config:
            raise ValueError("No backend configuration available")

        # Check if we already have an instance for this backend
        backend_key = f"{backend_config['name']}_{index}"
        if backend_key not in self.backends:
            # Create a new backend instance
            self.backends[backend_key] = LLMBackend(backend_config)

        return self.backends[backend_key]

    def get_vision_capable_backend(self, preferred_index: Optional[int] = None) -> LLMBackend:
        """Get a vision-capable backend, preferring the specified index.

        Args:
            preferred_index: Preferred backend index to try first.

        Returns:
            LLMBackend: Vision-capable backend instance.

        Raises:
            ValueError: If no vision-capable backend is found.
        """
        # Try preferred backend first if specified
        if preferred_index is not None:
            backend_config = self.config.get_backend(preferred_index)
            if backend_config and backend_config.get("supports_vision", False):
                return self.get_backend(preferred_index)

        # Find first vision-capable backend
        for i, candidate_config in enumerate(self.config.config["backends"]):
            if candidate_config.get("supports_vision", False):
                return self.get_backend(i)

        # No vision-capable backend found
        raise ValueError(
            "No vision-capable backend found. Please configure a backend with 'supports_vision: true'.\n\n"
            "Example configuration:\n"
            "backends:\n"
            '  - name: "openai-gpt4-vision"\n'
            '    model: "gpt-4-vision-preview"\n'
            "    supports_vision: true\n\n"
            "stdin:\n"
            "  default_backend_vision: 0"
        )
