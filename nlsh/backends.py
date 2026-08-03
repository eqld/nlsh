"""
LLM backend handling for nlsh.

This module provides functionality for interacting with different LLM backends.
"""

import re
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Optional

import openai

from nlsh.image_utils import prepare_image_for_api
from nlsh.structured import (
    JSON_OBJECT_INSTRUCTION,
    build_response_format,
    parse_command_response,
)


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
    """

    command: str
    danger_level: Optional[str] = None
    raw_response: str = ""


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

        # Structured output configuration (Phase 4). "auto" (default) tries
        # json_schema, then json_object, then falls back to legacy plain
        # text; the resolved working mode is cached for the lifetime of this
        # backend instance so we don't retry a known-unsupported mode on
        # every call (see generate_structured_command below).
        self.structured_output = config.get("structured_output", "auto")
        self._resolved_structured_mode: Optional[str] = None

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

        # Call the API with streaming
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            n=1,
            stream=True,
        )

        # Process the stream
        async for chunk in stream:
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
        # Call the API without streaming
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, max_tokens=max_tokens, n=1
        )

        # Extract and process the content
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content.strip()

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
            # Create messages for the chat completion
            messages = [{"role": "system", "content": system_context}]

            # Handle image input for vision models
            if image_data and image_mime_type:
                if not self.supports_vision():
                    raise ValueError(
                        f"Backend {self.name} does not support vision/image processing"
                    )

                # Prepare image for API
                base64_image, mime_type = prepare_image_for_api(image_data, image_mime_type)

                # Create user message with image
                user_message = {
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
            response = await self.client.chat.completions.create(
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
        replicating it for structured output, per the simplified design
        chosen for this phase. Structured output therefore only applies to
        non-verbose requests.

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

    def _calculate_temperature(self, regeneration_count: int) -> float:
        # Calculate temperature based on regeneration count (0.2 base, +0.1 per regeneration, max 1.0)
        return min(0.2 + (regeneration_count * 0.1), 1.0)

    def supports_vision(self) -> bool:
        """Check if this backend supports vision/image processing.

        Returns:
            bool: True if backend supports vision.
        """
        return self.config.get("supports_vision", False)


class BackendManager:
    """Manager for LLM backends."""

    def __init__(self, config):
        """Initialize the backend manager.

        Args:
            config: Configuration object.
        """
        self.config = config
        self.backends = {}

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
        for i, backend_config in enumerate(self.config.config["backends"]):
            if backend_config.get("supports_vision", False):
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
