import json
import sys

try:
    import llm
except ImportError:
    print(
        "The 'llm' module is not installed. Please install it using 'pip install llm'"
    )
    sys.exit(1)


def strip_markdown_json(text: str) -> str:
    """
    Strips markdown code blocks from LLM responses that wrap JSON.
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
    """
    print(f"Generating survey for: '{question}'...")
    # You might need to configure your LLM provider and model here.
    # For example, to use OpenAI: llm install openai
    # Then set the model: llm set-default openai-gpt-4
    # Or specify in the code: llm.get_model("openai-gpt-4")

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

    # Using the default model, or you can specify one:
    # model = llm.get_model("your-configured-model-name")
    # response = model.prompt(prompt)

    # For demonstration, we'll use the default model.
    # The response object from llm.prompt() has a .text property for the generated content.
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

    model = llm.get_model(model_name)
    response = model.prompt(prompt)

    # Handle both callable and property versions of response.text
    response_text = response.text() if callable(response.text) else response.text
    return response_text


def main():
    print("SurveyJS Chatbot")
    print("Type 'exit' to quit.")

    while True:
        user_question = input("\nEnter your survey question: ")
        if user_question.lower() == "exit":
            break

        try:
            survey_json_str = generate_survey_json(user_question)

            # Strip any markdown formatting that might wrap the JSON
            cleaned_json_str = strip_markdown_json(survey_json_str)

            # Attempt to parse the JSON to validate it
            survey_data = json.loads(cleaned_json_str)
            print("\nGenerated SurveyJS JSON:")
            print(json.dumps(survey_data, indent=2))

            save_option = input(
                "\nDo you want to save this JSON to a file? (yes/no): "
            ).lower()
            if save_option == "yes":
                file_name = input("Enter filename (e.g., my_survey.json): ")
                if not file_name.endswith(".json"):
                    file_name += ".json"

                with open(file_name, "w") as f:
                    json.dump(survey_data, f, indent=2)
                print(f"Survey JSON saved to {file_name}")

        except json.JSONDecodeError as e:
            print(
                "Error: Could not decode JSON from LLM response. Please try again or refine your question."
            )
            print(f"JSON decode error: {e}")
            if "cleaned_json_str" in locals():
                print(f"Cleaned LLM response:\n{cleaned_json_str}")
            else:
                print(f"Raw LLM response:\n{survey_json_str}")
        except ValueError as e:
            print(f"Configuration error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
