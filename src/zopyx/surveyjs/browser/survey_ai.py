import orjson
import plone.api
from zope.annotation.interfaces import IAnnotations

from ..audit import audit_form_version_change
from .services import ai as ai_service
from .services import forms as forms_service
from .views import Views


class SurveyAI(Views):
    """Dedicated browser view for @@ai and related AI AJAX endpoints."""

    def generate_ai_form(self):
        """Generate a SurveyJS form using AI based on user prompt."""

        try:
            from .ai_generator import generate_survey_json, strip_markdown_json
        except ImportError as e:
            error_result = {"error": "LLM module not available", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        prompt = self.request.form.get("prompt", "").strip()

        if not prompt:
            error_result = {
                "error": "No prompt provided",
                "message": "Please enter a description of the form you want to generate",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            model_name, api_key, ollama_url = ai_service.load_ai_settings()

            survey_json_str = generate_survey_json(
                prompt,
                model_name=model_name,
                api_key=api_key,
                ollama_url=ollama_url,
            )

            cleaned_json_str = strip_markdown_json(survey_json_str)
            survey_data = orjson.loads(cleaned_json_str)

            result = {"success": True, "json": survey_data}
            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {
                "error": "Invalid JSON generated",
                "message": f"The AI generated invalid JSON: {str(e)}",
                "raw_output": cleaned_json_str
                if "cleaned_json_str" in locals()
                else survey_json_str,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except ValueError as e:
            error_result = {"error": "Configuration error", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Generation failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def save_ai_form(self):
        """Save AI-generated form as a new version."""

        try:
            form_json_str = self.request.form.get("form_json", "")

            if not form_json_str:
                raise ValueError("No form JSON provided")

            json_form = orjson.loads(form_json_str)
            if not isinstance(json_form, dict):
                raise ValueError("Form JSON must be an object")

            annos = IAnnotations(self.context)
            previous_versions = forms_service.sorted_form_versions(annos)
            previous_version = previous_versions[-1] if previous_versions else None
            data = forms_service.save_form_version(
                annos,
                json_form,
                plone.api.user.get_current().getId(),
                locked=False,
            )
            audit_form_version_change(
                self.context,
                form_json=json_form,
                source="ai",
                new_version_id=data["id"],
                previous_version_id=previous_version["id"]
                if previous_version
                else None,
                previous_form_json=previous_version.get("form_json")
                if previous_version
                else None,
                locked=data.get("locked"),
            )

            result = dict(
                success=True, message="Form saved successfully", version_id=data["id"]
            )

            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {"error": "Invalid JSON", "message": str(e)}
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Save failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

    def refine_ai_form(self):
        """Refine an existing SurveyJS form based on user feedback."""

        try:
            from .ai_generator import refine_survey_json, strip_markdown_json
        except ImportError as e:
            error_result = {"error": "LLM module not available", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        current_json_str = self.request.form.get("current_json", "").strip()
        use_existing = self.request.form.get("use_existing", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        refinement_prompt = self.request.form.get("refinement_prompt", "").strip()

        if not current_json_str and use_existing:
            annos = IAnnotations(self.context)
            current_json = self._latest_form_json(annos)
            if not current_json:
                error_result = {
                    "error": "No existing form found",
                    "message": "No saved form version is available to refine",
                }
                self.request.response.setStatus(400)
                self.request.response.setHeader("content-type", "application/json")
                self.request.response.write(orjson.dumps(error_result))
                return
            current_json_str = orjson.dumps(current_json).decode("utf-8")

        if not current_json_str:
            error_result = {
                "error": "No current form provided",
                "message": "Current form JSON is required for refinement",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        if not refinement_prompt:
            error_result = {
                "error": "No refinement prompt provided",
                "message": "Please enter a description of the changes you want to make",
            }
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
            return

        try:
            current_json = orjson.loads(current_json_str)
            if not isinstance(current_json, dict):
                raise ValueError("Current form JSON must be an object")

            model_name, api_key, ollama_url = ai_service.load_ai_settings()

            refined_json_str = refine_survey_json(
                current_json,
                refinement_prompt,
                model_name=model_name,
                api_key=api_key,
                ollama_url=ollama_url,
            )

            cleaned_json_str = strip_markdown_json(refined_json_str)
            refined_data = orjson.loads(cleaned_json_str)

            if not isinstance(refined_data, dict):
                raise ValueError("Refined form must be a JSON object")

            result = {"success": True, "json": refined_data}

            self.request.response.setStatus(200)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(result))

        except orjson.JSONDecodeError as e:
            error_result = {
                "error": "Invalid JSON",
                "message": f"JSON parsing error: {str(e)}",
                "raw_output": cleaned_json_str
                if "cleaned_json_str" in locals()
                else refined_json_str
                if "refined_json_str" in locals()
                else current_json_str,
            }
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except ValueError as e:
            error_result = {"error": "Validation error", "message": str(e)}
            self.request.response.setStatus(400)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))

        except Exception as e:
            error_result = {"error": "Refinement failed", "message": str(e)}
            self.request.response.setStatus(500)
            self.request.response.setHeader("content-type", "application/json")
            self.request.response.write(orjson.dumps(error_result))
