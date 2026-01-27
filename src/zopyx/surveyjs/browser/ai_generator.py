"""
AI-powered form generation utilities.

This module provides functions for generating SurveyJS forms using LLM models.
Extracted from experimental/survey_bot.py for reuse in web views.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_attachment(path: str, mime_type: str):
    attachment_cls = None
    try:
        import llm

        attachment_cls = llm.Attachment
    except Exception:
        raise ImportError(
            "The 'llm' module is not installed. Please install it using 'pip install llm'"
        )

    if hasattr(attachment_cls, "from_path"):
        return attachment_cls.from_path(path)

    data = Path(path).read_bytes()
    filename = Path(path).name
    candidates = [
        lambda: attachment_cls(path=path),
        lambda: attachment_cls(data, mime_type, filename),
        lambda: attachment_cls(filename, data, mime_type),
        lambda: attachment_cls(data, filename=filename, mimetype=mime_type),
        lambda: attachment_cls(filename=filename, content=data, type=mime_type),
    ]
    for builder in candidates:
        try:
            return builder()
        except TypeError:
            continue
    try:
        import inspect

        sig = inspect.signature(attachment_cls)
        kwargs = {}
        for name in sig.parameters:
            if name in ("data", "content", "body", "bytes"):
                kwargs[name] = data
            elif name in ("filename", "name", "file_name"):
                kwargs[name] = filename
            elif name in ("path", "file", "file_path"):
                kwargs[name] = path
            elif name in ("mime_type", "mimetype", "content_type", "type"):
                kwargs[name] = mime_type
        if kwargs:
            return attachment_cls(**kwargs)
    except Exception:
        pass
    raise ValueError("Unsupported llm.Attachment constructor")


def strip_markdown_json(text: str) -> str:
    """
    Strips markdown code blocks from LLM responses that wrap JSON.

    Args:
        text: Response text from LLM that may contain markdown formatting

    Returns:
        Cleaned JSON string without markdown code block markers
    """
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def generate_survey_json(
    question: str, model_name: str = None, api_key: str = None, ollama_url: str = None
) -> str:
    """
    Generates SurveyJS JSON data based on a given question using the llm module.

    Args:
        question: Natural language description of the desired survey/form
        model_name: Optional LLM model to use (e.g., 'gpt-4', 'claude-3-sonnet-20240229').
                   If not provided, uses llm default model.
        api_key: Optional API key for the model provider. If not provided, uses
                environment variables or llm configured keys.
        ollama_url: Optional Ollama server URL (e.g., 'http://localhost:11434').
                   If provided, will use Ollama instead of other providers.

    Returns:
        JSON string containing the SurveyJS form definition

    Raises:
        ImportError: If llm module is not installed
        ValueError: If no model is configured or provided
        Exception: For other LLM-related errors
    """
    # Import llm here to provide better error messages
    try:
        import llm
    except ImportError:
        raise ImportError(
            "The 'llm' module is not installed. Please install it using 'pip install llm'"
        )

    # The prompt instructs the LLM to generate SurveyJS JSON.
    # It's crucial to guide the LLM to produce valid JSON.
    prompt = f"""
    Generate a SurveyJS JSON object for a survey based on the following question:
    "{question}"

    The JSON should represent a simple survey with one page and relevant question types (e.g., text, checkbox, radiobutton).
    Ensure the output is valid JSON and only the JSON. Do not include any additional text or markdown formatting outside the JSON object.
    Reason about fields belonging semantically together like lastname and firstname. These fields should be placed on the same row.
    Always include a hidden field "uuid" as string with an generated UUID4 as default and a hidden field "created" as str.
    Always use a dynamic matrix field where you can add, remote and edit rows for a given set of columns.
    Ensure that all fields and pages have proper titles and description.
    If the instructions for a form appear like a Survey, prefer a pagination per question.
    If the instructions are more a classic form and not a survey, use a one-pager.
    """

    logger.info("Generating survey JSON with LLM")
    logger.debug(
        f"Model: {model_name or 'default'}, Ollama URL: {ollama_url or 'none'}"
    )
    logger.debug(f"Prompt sent to LLM:\n{prompt}")

    # Determine which model to use
    if not model_name:
        # Fall back to llm default model
        try:
            model_name = llm.get_default_model()
            if not model_name:
                raise ValueError(
                    "No AI model configured. Please configure one in Site Setup > Forms or set a default using: llm set-default MODEL_NAME"
                )
        except Exception as e:
            raise ValueError(
                f"Failed to get AI model. Please configure one in Site Setup > Forms. Error: {e}"
            )

    # Generate the survey JSON
    try:
        # Configure Ollama if URL is provided
        if ollama_url:
            import os

            # Set Ollama base URL environment variable
            os.environ["OLLAMA_HOST"] = ollama_url

            # If model_name doesn't start with "ollama/", prepend it
            if model_name and not model_name.startswith("ollama/"):
                model_name = f"ollama/{model_name}"
            elif not model_name:
                # Default to a common Ollama model if none specified
                model_name = "ollama/llama2"

        model = llm.get_model(model_name)

        # Set API key if provided (for non-Ollama providers)
        if api_key and not ollama_url:
            # Try to set the key via environment for this request
            import os

            # Determine the env var name based on model provider
            if "gpt" in model_name.lower() or "openai" in model_name.lower():
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
                os.environ["ANTHROPIC_API_KEY"] = api_key
            # Add more providers as needed

        response = model.prompt(prompt)

        # Handle both callable and property versions of response.text
        response_text = response.text() if callable(response.text) else response.text

        logger.info("Successfully generated survey JSON")
        logger.debug(f"LLM response length: {len(response_text)} characters")

        return response_text
    except Exception as e:
        logger.error(f"Failed to generate form with model '{model_name}': {str(e)}")
        raise Exception(f"Failed to generate form with model '{model_name}': {str(e)}")


def generate_survey_json_from_image(
    image_path: str,
    prompt: str,
    model_name: str = None,
    api_key: str = None,
    ollama_url: str = None,
) -> str:
    """
    Generates SurveyJS JSON data based on an input image using the llm module.

    Args:
        image_path: Path to the PNG image to be analyzed
        prompt: Instruction prompt for the LLM
        model_name: Optional LLM model to use
        api_key: Optional API key for the model provider
        ollama_url: Optional Ollama server URL

    Returns:
        JSON string containing the SurveyJS form definition
    """
    try:
        import llm
    except ImportError:
        raise ImportError(
            "The 'llm' module is not installed. Please install it using 'pip install llm'"
        )

    try:
        attachment = _build_attachment(image_path, "image/png")
    except Exception as e:
        raise ValueError(f"Failed to attach image for LLM processing: {str(e)}")

    logger.info("Generating survey JSON from image with LLM")
    logger.debug(
        f"Model: {model_name or 'default'}, Ollama URL: {ollama_url or 'none'}"
    )
    print(f"LLM prompt (image):\n{prompt}")

    # Determine which model to use
    if not model_name:
        # Fall back to llm default model
        try:
            model_name = llm.get_default_model()
            if not model_name:
                raise ValueError(
                    "No AI model configured. Please configure one in Site Setup > Forms or set a default using: llm set-default MODEL_NAME"
                )
        except Exception as e:
            raise ValueError(
                f"Failed to get AI model. Please configure one in Site Setup > Forms. Error: {e}"
            )

    try:
        if ollama_url:
            import os

            os.environ["OLLAMA_HOST"] = ollama_url
            if model_name and not model_name.startswith("ollama/"):
                model_name = f"ollama/{model_name}"
            elif not model_name:
                model_name = "ollama/llama2"

        model = llm.get_model(model_name)

        if api_key and not ollama_url:
            import os

            if "gpt" in model_name.lower() or "openai" in model_name.lower():
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
                os.environ["ANTHROPIC_API_KEY"] = api_key

        response = model.prompt(prompt, attachments=[attachment])
        response_text = response.text() if callable(response.text) else response.text

        logger.info("Successfully generated survey JSON from image")
        logger.debug(f"LLM response length: {len(response_text)} characters")
        print(f"LLM response (image):\n{response_text}")

        return response_text
    except Exception as e:
        logger.error(f"Failed to generate form with model '{model_name}': {str(e)}")
        raise Exception(f"Failed to generate form with model '{model_name}': {str(e)}")


def generate_survey_json_from_assets(
    png_paths: list[str],
    prompt: str,
    model_name: str = None,
    api_key: str = None,
    ollama_url: str = None,
) -> str:
    """
    Generates SurveyJS JSON data based on PNG pages and extracted PDF form JSON.

    Args:
        png_paths: List of PNG file paths to be analyzed
        prompt: Instruction prompt for the LLM
        model_name: Optional LLM model to use
        api_key: Optional API key for the model provider
        ollama_url: Optional Ollama server URL

    Returns:
        JSON string containing the SurveyJS form definition
    """
    try:
        import llm
    except ImportError:
        raise ImportError(
            "The 'llm' module is not installed. Please install it using 'pip install llm'"
        )

    attachments = []
    for path in png_paths:
        attachments.append(_build_attachment(path, "image/png"))

    logger.info("Generating survey JSON from PDF assets with LLM")
    logger.debug(
        f"Model: {model_name or 'default'}, Ollama URL: {ollama_url or 'none'}"
    )
    print(f"LLM prompt (pdf assets):\n{prompt}")

    if not model_name:
        try:
            model_name = llm.get_default_model()
            if not model_name:
                raise ValueError(
                    "No AI model configured. Please configure one in Site Setup > Forms or set a default using: llm set-default MODEL_NAME"
                )
        except Exception as e:
            raise ValueError(
                f"Failed to get AI model. Please configure one in Site Setup > Forms. Error: {e}"
            )

    try:
        if ollama_url:
            import os

            os.environ["OLLAMA_HOST"] = ollama_url
            if model_name and not model_name.startswith("ollama/"):
                model_name = f"ollama/{model_name}"
            elif not model_name:
                model_name = "ollama/llama2"

        model = llm.get_model(model_name)

        if api_key and not ollama_url:
            import os

            if "gpt" in model_name.lower() or "openai" in model_name.lower():
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
                os.environ["ANTHROPIC_API_KEY"] = api_key

        response = model.prompt(prompt, attachments=attachments)
        response_text = response.text() if callable(response.text) else response.text

        logger.info("Successfully generated survey JSON from PDF assets")
        logger.debug(f"LLM response length: {len(response_text)} characters")
        print(f"LLM response (pdf assets):\n{response_text}")

        return response_text
    except Exception as e:
        logger.error(f"Failed to generate form with model '{model_name}': {str(e)}")
        raise Exception(f"Failed to generate form with model '{model_name}': {str(e)}")


def refine_survey_json(
    current_json: dict,
    refinement_prompt: str,
    model_name: str = None,
    api_key: str = None,
    ollama_url: str = None,
) -> str:
    """
    Refines an existing SurveyJS form based on user feedback.

    Args:
        current_json: The current form JSON dict to refine
        refinement_prompt: Natural language description of desired changes
        model_name: Optional LLM model to use (e.g., 'gpt-4', 'claude-3-sonnet-20240229').
                   If not provided, uses llm default model.
        api_key: Optional API key for the model provider. If not provided, uses
                environment variables or llm configured keys.
        ollama_url: Optional Ollama server URL (e.g., 'http://localhost:11434').
                   If provided, will use Ollama instead of other providers.

    Returns:
        JSON string containing the refined SurveyJS form definition

    Raises:
        ImportError: If llm module is not installed
        ValueError: If no model is configured or provided
        Exception: For other LLM-related errors
    """
    # Import llm here to provide better error messages
    try:
        import llm
    except ImportError:
        raise ImportError(
            "The 'llm' module is not installed. Please install it using 'pip install llm'"
        )

    import json

    # Construct refinement prompt that includes context
    prompt = f"""
    You are refining an existing SurveyJS form. Here is the current form definition:

    {json.dumps(current_json, indent=2)}

    The user wants to make the following changes:
    "{refinement_prompt}"

    Please modify the form JSON according to the user's request. Return ONLY the complete updated JSON.
    Important guidelines:
    - Maintain all existing fields unless explicitly asked to change or remove them
    - Preserve the form structure, field names, and IDs where possible
    - Keep the hidden "uuid" and "created" fields
    - Ensure the output is valid JSON with no additional text or markdown formatting
    - Apply the requested changes while maintaining form coherence
    - If adding new fields, follow the same patterns as existing fields
    - Use semantic grouping (e.g., related fields on the same row)
    """

    logger.info("Refining survey JSON with LLM")
    logger.debug(
        f"Model: {model_name or 'default'}, Ollama URL: {ollama_url or 'none'}"
    )
    logger.debug(f"Refinement request: {refinement_prompt}")
    logger.debug(f"Prompt sent to LLM:\n{prompt}")

    # Determine which model to use
    if not model_name:
        # Fall back to llm default model
        try:
            model_name = llm.get_default_model()
            if not model_name:
                raise ValueError(
                    "No AI model configured. Please configure one in Site Setup > Forms or set a default using: llm set-default MODEL_NAME"
                )
        except Exception as e:
            raise ValueError(
                f"Failed to get AI model. Please configure one in Site Setup > Forms. Error: {e}"
            )

    # Refine the survey JSON
    try:
        # Configure Ollama if URL is provided
        if ollama_url:
            import os

            # Set Ollama base URL environment variable
            os.environ["OLLAMA_HOST"] = ollama_url

            # If model_name doesn't start with "ollama/", prepend it
            if model_name and not model_name.startswith("ollama/"):
                model_name = f"ollama/{model_name}"
            elif not model_name:
                # Default to a common Ollama model if none specified
                model_name = "ollama/llama2"

        model = llm.get_model(model_name)

        # Set API key if provided (for non-Ollama providers)
        if api_key and not ollama_url:
            # Try to set the key via environment for this request
            import os

            # Determine the env var name based on model provider
            if "gpt" in model_name.lower() or "openai" in model_name.lower():
                os.environ["OPENAI_API_KEY"] = api_key
            elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
                os.environ["ANTHROPIC_API_KEY"] = api_key
            # Add more providers as needed

        response = model.prompt(prompt)

        # Handle both callable and property versions of response.text
        response_text = response.text() if callable(response.text) else response.text

        logger.info("Successfully refined survey JSON")
        logger.debug(f"LLM response length: {len(response_text)} characters")

        return response_text
    except Exception as e:
        logger.error(f"Failed to refine form with model '{model_name}': {str(e)}")
        raise Exception(f"Failed to refine form with model '{model_name}': {str(e)}")
