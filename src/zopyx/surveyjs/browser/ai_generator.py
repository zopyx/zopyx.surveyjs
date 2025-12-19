"""
AI-powered form generation utilities.

This module provides functions for generating SurveyJS forms using LLM models.
Extracted from experimental/survey_bot.py for reuse in web views.
"""


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
    question: str, model_name: str = None, api_key: str = None
) -> str:
    """
    Generates SurveyJS JSON data based on a given question using the llm module.

    Args:
        question: Natural language description of the desired survey/form
        model_name: Optional LLM model to use (e.g., 'gpt-4', 'claude-3-sonnet-20240229').
                   If not provided, uses llm default model.
        api_key: Optional API key for the model provider. If not provided, uses
                environment variables or llm configured keys.

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
    """

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
        model = llm.get_model(model_name)

        # Set API key if provided
        if api_key:
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
        return response_text
    except Exception as e:
        raise Exception(f"Failed to generate form with model '{model_name}': {str(e)}")


def refine_survey_json(
    current_json: dict, refinement_prompt: str, model_name: str = None, api_key: str = None
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
        model = llm.get_model(model_name)

        # Set API key if provided
        if api_key:
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
        return response_text
    except Exception as e:
        raise Exception(f"Failed to refine form with model '{model_name}': {str(e)}")
