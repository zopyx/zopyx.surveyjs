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


def generate_survey_json(question: str) -> str:
    """
    Generates SurveyJS JSON data based on a given question using the llm module.

    Args:
        question: Natural language description of the desired survey/form

    Returns:
        JSON string containing the SurveyJS form definition

    Raises:
        ImportError: If llm module is not installed
        ValueError: If no default LLM model is configured
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
    """

    # Get the default model
    try:
        model_name = llm.get_default_model()
        if not model_name:
            raise ValueError(
                "No default LLM model configured. Please set one using: llm set-default MODEL_NAME"
            )
    except Exception as e:
        raise ValueError(
            f"Failed to get default model. Please configure a model using: llm set-default MODEL_NAME. Error: {e}"
        )

    # Generate the survey JSON
    model = llm.get_model(model_name)
    response = model.prompt(prompt)

    # Handle both callable and property versions of response.text
    response_text = response.text() if callable(response.text) else response.text
    return response_text
