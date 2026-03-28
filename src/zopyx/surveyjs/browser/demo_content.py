from datetime import datetime, timezone
from pathlib import Path
import logging
import uuid

from plone.protect.interfaces import IDisableCSRFProtection
from zope.annotation.interfaces import IAnnotations
from zope.interface import alsoProvides
from BTrees.OOBTree import OOBTree
import plone.api
from Products.Five import BrowserView

from ..constants import RESULTS_KEY
from ..content.survey import Counter
from ..storage import get_result_storage
from .services import forms as forms_service
from .services.http import json_response

logger = logging.getLogger(__name__)


class DemoContent(BrowserView):
    """Browser view to generate demo content for testing."""

    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)
        portal = plone.api.portal.get()

        existing = portal.get("demos")
        if existing is not None:
            plone.api.content.delete(obj=existing)

        demos = plone.api.content.create(
            type="Folder",
            container=portal,
            id="demos",
            title="Demos",
        )
        try:
            demos.language = "de"
            demos.reindexObject(idxs=["Language"])
        except Exception as e:
            logger.debug("Failed to set demo folder language: %s", e)
        try:
            demos.exclude_from_nav = True
            demos.reindexObject(idxs=["exclude_from_nav"])
        except Exception as e:
            logger.debug("Failed to exclude demo folder from nav: %s", e)
        self._ensure_private(demos)

        created = []
        errors = []
        current_user = plone.api.user.get_current()
        user_id = current_user.getId() if current_user else ""

        # Generate multilingual demo survey
        try:
            form_json = self._generate_multilingual_demo_survey()
            survey_id = "multilingual-demo-survey"

            survey = plone.api.content.create(
                type="Survey",
                container=demos,
                id=survey_id,
                title="Multilingual Demo Survey",
            )
            try:
                survey.language = "en"
                survey.reindexObject(idxs=["Language"])
            except Exception as e:
                logger.debug("Failed to set survey language: %s", e)
            try:
                survey.exclude_from_nav = True
                survey.reindexObject(idxs=["exclude_from_nav"])
            except Exception as e:
                logger.debug("Failed to exclude survey from nav: %s", e)
            try:
                locales = (
                    form_json.get("locales") if isinstance(form_json, dict) else None
                )
                if not isinstance(locales, list) or not locales:
                    fallback_locale = (
                        form_json.get("locale") if isinstance(form_json, dict) else None
                    ) or "en"
                    locales = [fallback_locale]
                survey.survey_languages = [
                    str(code).strip().lower().split("-", 1)[0]
                    for code in locales
                    if str(code).strip()
                ]
            except Exception as e:
                logger.debug("Failed to set survey languages: %s", e)
            self._ensure_private(survey)
            annos = IAnnotations(survey)
            forms_service.save_form_version(
                annos,
                form_json,
                user_id,
                locked=False,
            )

            # Generate 100 random demo results for multilingual survey
            self._generate_demo_results(survey, form_json, count=100)

            created.append({"id": survey_id, "title": "Multilingual Demo Survey"})
        except Exception as exc:
            errors.append({"path": "generated", "error": str(exc)})

        # Generate SurveyJS demo survey with various question types
        try:
            form_json = self._generate_surveyjs_demo_survey()
            survey_id = "surveyjs-demo-survey"

            survey = plone.api.content.create(
                type="Survey",
                container=demos,
                id=survey_id,
                title="SurveyJS Demo - Various Question Types",
            )
            try:
                survey.language = "en"
                survey.reindexObject(idxs=["Language"])
            except Exception as e:
                logger.debug("Failed to set survey language: %s", e)
            try:
                survey.exclude_from_nav = True
                survey.reindexObject(idxs=["exclude_from_nav"])
            except Exception as e:
                logger.debug("Failed to exclude survey from nav: %s", e)
            try:
                survey.survey_languages = ["en"]
            except Exception as e:
                logger.debug("Failed to set survey languages: %s", e)
            self._ensure_private(survey)
            annos = IAnnotations(survey)
            forms_service.save_form_version(
                annos,
                form_json,
                user_id,
                locked=False,
            )

            # Generate 100 random demo results for this survey
            self._generate_demo_results(survey, form_json, count=100)

            created.append(
                {"id": survey_id, "title": "SurveyJS Demo - Various Question Types"}
            )
        except Exception as exc:
            errors.append({"path": "surveyjs-demo", "error": str(exc)})

        # Create prefilled address survey
        try:
            survey, error = self._create_prefilled_survey(demos, user_id)
            if survey:
                created.append({"id": "prefilled", "title": "Prefilled Address Book"})
            elif error:
                errors.append({"path": "prefilled", "error": error})
        except Exception as exc:
            errors.append({"path": "prefilled", "error": str(exc)})

        json_response(
            self.request.response,
            {
                "folder": "demos",
                "created": created,
                "errors": errors,
                "count": len(created),
            },
        )

    def _ensure_private(self, obj):
        """Ensure the object is in private state."""
        try:
            state = plone.api.content.get_state(obj)
        except Exception as e:
            logger.debug("Failed to get workflow state: %s", e)
            return False
        if state == "private":
            return True
        try:
            transitions = plone.api.content.get_transitions(obj)
        except Exception as e:
            logger.debug("Failed to get workflow transitions: %s", e)
            transitions = []
        transition_ids = {item.get("id") for item in transitions if item.get("id")}
        for candidate in ("retract", "hide", "make-private"):
            if candidate in transition_ids:
                try:
                    plone.api.content.transition(obj=obj, transition=candidate)
                    return True
                except Exception as e:
                    logger.debug("Workflow transition %s failed: %s", candidate, e)
                    continue
        return False

    def _generate_multilingual_demo_survey(self):
        """Generate a multilingual survey with 3 random questions and 3 answer choices.

        Supports: DE, SQ (Albanian), EN, FR, HR (Croatian), PL, RU, SR, TR, VI
        """
        import random

        # Translations dictionary
        translations = {
            "survey_title": {
                "default": "Customer Satisfaction Survey",
                "de": "Kundenzufriedenheitsumfrage",
                "sq": "Anketa e kënaqësisë së klientit",
                "fr": "Enquête de satisfaction client",
                "hr": "Anketa zadovoljstva korisnika",
                "pl": "Ankieta satysfakcji klienta",
                "ru": "Опрос удовлетворенности клиентов",
                "sr": "Anketa o zadovoljstvu kupaca",
                "tr": "Müşteri Memnuniyeti Anketi",
                "vi": "Khảo sát sự hài lòng của khách hàng",
            },
            "survey_description": {
                "default": "Please share your feedback to help us improve our services.",
                "de": "Bitte teilen Sie uns Ihr Feedback mit, um unsere Dienstleistungen zu verbessern.",
                "sq": "Ju lutemi ndani mendimin tuaj për të na ndihmuar të përmirësojmë shërbimet tona.",
                "fr": "Veuillez partager vos commentaires pour nous aider à améliorer nos services.",
                "hr": "Molimo podijelite svoje povratne informacije kako bismo poboljšali naše usluge.",
                "pl": "Prosimy o podzielenie się opinią, aby pomóc nam ulepszyć nasze usługi.",
                "ru": "Пожалуйста, поделитесь своими отзывами, чтобы помочь нам улучшить наши услуги.",
                "sr": "Molimo vas da podelite svoje mišljenje kako bismo unapredili naše usluge.",
                "tr": "Hizmetlerimizi geliştirmemize yardımcı olmak için lütfen geri bildiriminizi paylaşın.",
                "vi": "Vui lòng chia sẻ phản hồi của bạn để giúp chúng tôi cải thiện dịch vụ.",
            },
            "page_title": {
                "default": "Survey Questions",
                "de": "Umfragefragen",
                "sq": "Pyetjet e anketës",
                "fr": "Questions de l'enquête",
                "hr": "Anketna pitanja",
                "pl": "Pytania ankiety",
                "ru": "Вопросы опроса",
                "sr": "Pitanja ankete",
                "tr": "Anket Soruları",
                "vi": "Câu hỏi khảo sát",
            },
            # Question 1: Service Quality
            "question1_title": {
                "default": "How would you rate the quality of our service?",
                "de": "Wie würden Sie die Qualität unserer Dienstleistung bewerten?",
                "sq": "Si do ta vlerësonit cilësinë e shërbimit tonë?",
                "fr": "Comment évalueriez-vous la qualité de notre service ?",
                "hr": "Kako biste ocijenili kvalitetu naše usluge?",
                "pl": "Jak oceniasz jakość naszych usług?",
                "ru": "Как бы вы оценили качество нашего обслуживания?",
                "sr": "Kako biste ocenili kvalitet naše usluge?",
                "tr": "Hizmet kalitemizi nasıl değerlendirirsiniz?",
                "vi": "Bạn đánh giá chất lượng dịch vụ của chúng tôi như thế nào?",
            },
            # Question 2: Product Satisfaction
            "question2_title": {
                "default": "How satisfied are you with our product?",
                "de": "Wie zufrieden sind Sie mit unserem Produkt?",
                "sq": "Sa të kënaqur jeni me produktin tonë?",
                "fr": "Êtes-vous satisfait de notre produit ?",
                "hr": "Koliko ste zadovoljni našim proizvodom?",
                "pl": "Jak bardzo jesteś zadowolony z naszego produktu?",
                "ru": "Насколько вы довольны нашим продуктом?",
                "sr": "Koliko ste zadovoljni našim proizvodom?",
                "tr": "Ürünümüzden ne kadar memnunsunuz?",
                "vi": "Bạn hài lòng với sản phẩm của chúng tôi đến mức nào?",
            },
            # Question 3: Recommendation
            "question3_title": {
                "default": "Would you recommend us to others?",
                "de": "Würden Sie uns anderen weiterempfehlen?",
                "sq": "A do të na rekomandonit tek të tjerët?",
                "fr": "Nous recommanderiez-vous à d'autres ?",
                "hr": "Biste li nas preporučili drugima?",
                "pl": "Czy poleciłbyś nas innym?",
                "ru": "Порекомендуете ли вы нас другим?",
                "sr": "Da li biste nas preporučili drugima?",
                "tr": "Bizi başkalarına tavsiye eder misiniz?",
                "vi": "Bạn có giới thiệu chúng tôi với người khác không?",
            },
            # Answer choices
            "excellent": {
                "default": "Excellent",
                "de": "Ausgezeichnet",
                "sq": "Shkëlqyeshëm",
                "fr": "Excellent",
                "hr": "Odlično",
                "pl": "Doskonałe",
                "ru": "Отлично",
                "sr": "Odlično",
                "tr": "Mükemmel",
                "vi": "Xuất sắc",
            },
            "good": {
                "default": "Good",
                "de": "Gut",
                "sq": "Mirë",
                "fr": "Bon",
                "hr": "Dobro",
                "pl": "Dobre",
                "ru": "Хорошо",
                "sr": "Dobro",
                "tr": "İyi",
                "vi": "Tốt",
            },
            "average": {
                "default": "Average",
                "de": "Durchschnittlich",
                "sq": "Mesatare",
                "fr": "Moyen",
                "hr": "Prosječno",
                "pl": "Przeciętne",
                "ru": "Средне",
                "sr": "Prosečno",
                "tr": "Ortalama",
                "vi": "Trung bình",
            },
            "poor": {
                "default": "Poor",
                "de": "Schlecht",
                "sq": "Dobët",
                "fr": "Faible",
                "hr": "Loše",
                "pl": "Słabe",
                "ru": "Плохо",
                "sr": "Loše",
                "tr": "Zayıf",
                "vi": "Kém",
            },
            "very_satisfied": {
                "default": "Very Satisfied",
                "de": "Sehr zufrieden",
                "sq": "Shumë i kënaqur",
                "fr": "Très satisfait",
                "hr": "Vrlo zadovoljan",
                "pl": "Bardzo zadowolony",
                "ru": "Очень доволен",
                "sr": "Veoma zadovoljan",
                "tr": "Çok Memnun",
                "vi": "Rất hài lòng",
            },
            "satisfied": {
                "default": "Satisfied",
                "de": "Zufrieden",
                "sq": "I kënaqur",
                "fr": "Satisfait",
                "hr": "Zadovoljan",
                "pl": "Zadowolony",
                "ru": "Доволен",
                "sr": "Zadovoljan",
                "tr": "Memnun",
                "vi": "Hài lòng",
            },
            "dissatisfied": {
                "default": "Dissatisfied",
                "de": "Unzufrieden",
                "sq": "I pakënaqur",
                "fr": "Insatisfait",
                "hr": "Nezadovoljan",
                "pl": "Niezadowolony",
                "ru": "Недоволен",
                "sr": "Nezadovoljan",
                "tr": "Memnun değil",
                "vi": "Không hài lòng",
            },
            "definitely_yes": {
                "default": "Definitely Yes",
                "de": "Definitiv ja",
                "sq": "Patjetër po",
                "fr": "Définitivement oui",
                "hr": "Definitivno da",
                "pl": "Zdecydowanie tak",
                "ru": "Определенно да",
                "sr": "Definitivno da",
                "tr": "Kesinlikle Evet",
                "vi": "Chắc chắn có",
            },
            "probably_yes": {
                "default": "Probably Yes",
                "de": "Wahrscheinlich ja",
                "sq": "Ndoshta po",
                "fr": "Probablement oui",
                "hr": "Vjerojatno da",
                "pl": "Prawdopodobnie tak",
                "ru": "Вероятно да",
                "sr": "Verovatno da",
                "tr": "Muhtemelen Evet",
                "vi": "Có lẽ có",
            },
            "not_sure": {
                "default": "Not Sure",
                "de": "Nicht sicher",
                "sq": "Nuk jam i sigurt",
                "fr": "Pas sûr",
                "hr": "Nisam siguran",
                "pl": "Nie jestem pewien",
                "ru": "Не уверен",
                "sr": "Nisam siguran",
                "tr": "Emin Değilim",
                "vi": "Không chắc",
            },
            "probably_not": {
                "default": "Probably Not",
                "de": "Wahrscheinlich nicht",
                "sq": "Ndoshta jo",
                "fr": "Probablement pas",
                "hr": "Vjerojatno ne",
                "pl": "Prawdopodobnie nie",
                "ru": "Вероятно нет",
                "sr": "Verovatno ne",
                "tr": "Muhtemelen Hayır",
                "vi": "Có lẽ không",
            },
            "definitely_not": {
                "default": "Definitely Not",
                "de": "Definitiv nicht",
                "sq": "Patjetër jo",
                "fr": "Définitivement pas",
                "hr": "Definitivno ne",
                "pl": "Zdecydowanie nie",
                "ru": "Определенно нет",
                "sr": "Definitivno ne",
                "tr": "Kesinlikle Hayır",
                "vi": "Chắc chắn không",
            },
            "complete": {
                "default": "Complete",
                "de": "Abschließen",
                "sq": "Përfundo",
                "fr": "Terminer",
                "hr": "Završi",
                "pl": "Zakończ",
                "ru": "Завершить",
                "sr": "Završi",
                "tr": "Tamamla",
                "vi": "Hoàn thành",
            },
            "page_next": {
                "default": "Next",
                "de": "Weiter",
                "sq": "Tjetër",
                "fr": "Suivant",
                "hr": "Dalje",
                "pl": "Dalej",
                "ru": "Далее",
                "sr": "Dalje",
                "tr": "İleri",
                "vi": "Tiếp theo",
            },
            "page_prev": {
                "default": "Previous",
                "de": "Zurück",
                "sq": "Mbrapa",
                "fr": "Précédent",
                "hr": "Natrag",
                "pl": "Wstecz",
                "ru": "Назад",
                "sr": "Nazad",
                "tr": "Geri",
                "vi": "Quay lại",
            },
        }

        # Question pool with translations
        question_pool = [
            {
                "name": "service_quality",
                "title": translations["question1_title"],
                "choices": [
                    {"value": "excellent", "text": translations["excellent"]},
                    {"value": "good", "text": translations["good"]},
                    {"value": "average", "text": translations["average"]},
                    {"value": "poor", "text": translations["poor"]},
                ],
            },
            {
                "name": "product_satisfaction",
                "title": translations["question2_title"],
                "choices": [
                    {"value": "very_satisfied", "text": translations["very_satisfied"]},
                    {"value": "satisfied", "text": translations["satisfied"]},
                    {"value": "average", "text": translations["average"]},
                    {"value": "dissatisfied", "text": translations["dissatisfied"]},
                ],
            },
            {
                "name": "recommendation",
                "title": translations["question3_title"],
                "choices": [
                    {"value": "definitely_yes", "text": translations["definitely_yes"]},
                    {"value": "probably_yes", "text": translations["probably_yes"]},
                    {"value": "not_sure", "text": translations["not_sure"]},
                    {"value": "probably_not", "text": translations["probably_not"]},
                    {"value": "definitely_not", "text": translations["definitely_not"]},
                ],
            },
        ]

        # Select 3 random questions
        selected_questions = random.sample(question_pool, min(3, len(question_pool)))

        # Build survey elements
        elements = []
        for q in selected_questions:
            elements.append(
                {
                    "type": "radiogroup",
                    "name": q["name"],
                    "title": q["title"],
                    "isRequired": True,
                    "choices": q["choices"],
                    "colCount": 1,
                }
            )

        # Build survey JSON
        survey_json = {
            "title": translations["survey_title"],
            "description": translations["survey_description"],
            "locale": "en",
            "locales": ["en", "de", "sq", "fr", "hr", "pl", "ru", "sr", "tr", "vi"],
            "showQuestionNumbers": "on",
            "completeText": translations["complete"],
            "pageNextText": translations["page_next"],
            "pagePrevText": translations["page_prev"],
            "pages": [
                {
                    "name": "page1",
                    "title": translations["page_title"],
                    "elements": elements,
                }
            ],
        }

        return survey_json

    def _generate_surveyjs_demo_survey(self):
        """Generate a SurveyJS demo survey with various question types.

        Demonstrates: radiogroup, checkbox, rating, text, comment, boolean
        """
        survey_json = {
            "title": "Employee Satisfaction Survey",
            "description": "Help us understand your workplace experience by answering these questions.",
            "locale": "en",
            "showQuestionNumbers": "on",
            "completeText": "Submit",
            "pages": [
                {
                    "name": "page1",
                    "title": "Work Environment",
                    "elements": [
                        {
                            "type": "radiogroup",
                            "name": "department",
                            "title": "Which department do you work in?",
                            "isRequired": True,
                            "choices": [
                                {"value": "engineering", "text": "Engineering"},
                                {"value": "sales", "text": "Sales"},
                                {"value": "marketing", "text": "Marketing"},
                                {"value": "hr", "text": "Human Resources"},
                                {"value": "finance", "text": "Finance"},
                                {"value": "operations", "text": "Operations"},
                            ],
                            "colCount": 2,
                        },
                        {
                            "type": "checkbox",
                            "name": "benefits",
                            "title": "Which benefits do you value most? (Select up to 3)",
                            "isRequired": True,
                            "choices": [
                                {"value": "health", "text": "Health Insurance"},
                                {"value": "remote", "text": "Remote Work Options"},
                                {"value": "flexible", "text": "Flexible Hours"},
                                {"value": "training", "text": "Professional Training"},
                                {"value": "bonus", "text": "Performance Bonus"},
                                {"value": "vacation", "text": "Extra Vacation Days"},
                            ],
                            "maxSelectedChoices": 3,
                        },
                    ],
                },
                {
                    "name": "page2",
                    "title": "Job Satisfaction",
                    "elements": [
                        {
                            "type": "rating",
                            "name": "satisfaction",
                            "title": "How satisfied are you with your current role?",
                            "isRequired": True,
                            "rateMin": 1,
                            "rateMax": 5,
                            "minRateDescription": "Very Dissatisfied",
                            "maxRateDescription": "Very Satisfied",
                        },
                        {
                            "type": "rating",
                            "name": "work_life_balance",
                            "title": "Rate your work-life balance",
                            "isRequired": True,
                            "rateType": "stars",
                            "rateCount": 5,
                        },
                        {
                            "type": "boolean",
                            "name": "recommend",
                            "title": "Would you recommend this company to a friend?",
                            "isRequired": True,
                            "labelTrue": "Yes",
                            "labelFalse": "No",
                        },
                    ],
                },
                {
                    "name": "page3",
                    "title": "Feedback",
                    "elements": [
                        {
                            "type": "text",
                            "name": "years_service",
                            "title": "How many years have you been with the company?",
                            "isRequired": True,
                            "inputType": "number",
                            "min": 0,
                            "max": 50,
                        },
                        {
                            "type": "comment",
                            "name": "improvements",
                            "title": "What improvements would you suggest for the workplace?",
                            "isRequired": False,
                            "rows": 4,
                            "placeholder": "Share your ideas here...",
                        },
                    ],
                },
            ],
        }

        return survey_json

    def _generate_demo_results(self, survey, form_json, count=100):
        """Generate random demo results for a survey."""
        import random
        from datetime import datetime, timezone, timedelta
        import uuid

        storage = get_result_storage(survey)

        # Parse form structure to understand questions
        pages = form_json.get("pages", [])
        questions = []
        for page in pages:
            for element in page.get("elements", []):
                questions.append(element)

        # Get supported locales from form_json for multilingual surveys
        locales = form_json.get("locales", [])
        if not locales:
            locales = [form_json.get("locale", "en")]

        # Multilingual comments for different languages
        multilingual_comments = {
            "en": [
                "Excellent service, very satisfied!",
                "Good experience overall.",
                "Could be better, had some issues.",
                "Not happy with the service.",
                "Average experience, nothing special.",
                "Would recommend to friends.",
                "Fast and efficient service.",
                "Staff was very helpful.",
                "Room for improvement.",
                "No comments at this time.",
            ],
            "de": [
                "Ausgezeichneter Service, sehr zufrieden!",
                "Insgesamt gute Erfahrung.",
                "Könnte besser sein, hatte einige Probleme.",
                "Nicht zufrieden mit dem Service.",
                "Durchschnittliche Erfahrung, nichts Besonderes.",
                "Würde ich Freunden empfehlen.",
                "Schneller und effizienter Service.",
                "Personal war sehr hilfreich.",
                "Verbesserungspotenzial vorhanden.",
                "Keine Anmerkungen.",
            ],
            "fr": [
                "Service excellent, très satisfait!",
                "Bonne expérience globale.",
                "Pourrait être mieux, quelques problèmes.",
                "Pas satisfait du service.",
                "Expérience moyenne, rien de spécial.",
                "Je recommanderais à des amis.",
                "Service rapide et efficace.",
                "Le personnel était très serviable.",
                "Marge d'amélioration.",
                "Pas de commentaires.",
            ],
            "sq": [
                "Shërbim i shkëlqyer, shumë i kënaqur!",
                "Përvojë e mirë në përgjithësi.",
                "Mund të ishte më mirë, kisha disa probleme.",
                "Jo i kënaqur me shërbimin.",
                "Përvojë mesatare, asgjë e veçantë.",
                "Do ta rekomandoja miqve.",
                "Shërbim i shpejtë dhe efikas.",
                "Stafi ishte shumë i ndihmueshëm.",
                "Hapsirë për përmirësim.",
                "Asnjë koment në këtë moment.",
            ],
            "hr": [
                "Izvrsna usluga, vrlo zadovoljan!",
                "Dobro iskustvo u cjelini.",
                "Moglo bi biti bolje, imao sam nekih problema.",
                "Nisam zadovoljan uslugom.",
                "Prosječno iskustvo, ništa posebno.",
                "Preporučio bih prijateljima.",
                "Brza i učinkovita usluga.",
                "Osoblje je bilo vrlo uslužno.",
                "Prostor za poboljšanje.",
                "Nema komentara.",
            ],
            "pl": [
                "Doskonała obsługa, bardzo zadowolony!",
                "Dobre doświadczenie ogólnie.",
                "Mogłoby być lepiej, miałem pewne problemy.",
                "Niezadowolony z usługi.",
                "Przeciętne doświadczenie, nic specjalnego.",
                "Poleciłbym znajomym.",
                "Szybka i wydajna obsługa.",
                "Personel był bardzo pomocny.",
                "Miejsce na poprawę.",
                "Brak uwag.",
            ],
            "ru": [
                "Отличный сервис, очень доволен!",
                "Хороший опыт в целом.",
                "Могло быть лучше, были проблемы.",
                "Не доволен обслуживанием.",
                "Средний опыт, ничего особенного.",
                "Рекомендовал бы друзьям.",
                "Быстрое и эффективное обслуживание.",
                "Персонал был очень полезен.",
                "Есть над чем работать.",
                "Без комментариев.",
            ],
            "sr": [
                "Odlična usluga, veoma zadovoljan!",
                "Dobro iskustvo u celini.",
                "Moglo bi bolje, imao sam nekih problema.",
                "Nisam zadovoljan uslugom.",
                "Prosečno iskustvo, ništa posebno.",
                "Preporučio bih prijateljima.",
                "Brza i efikasna usluga.",
                "Osoblje je bilo veoma uslužno.",
                "Prostor za unapređenje.",
                "Nema komentara.",
            ],
            "tr": [
                "Mükemmel hizmet, çok memnun!",
                "Genel olarak iyi deneyim.",
                "Daha iyi olabilirdi, bazı sorunlar vardı.",
                "Hizmetten memnun değilim.",
                "Ortalama deneyim, özel bir şey yok.",
                "Arkadaşlarıma tavsiye ederim.",
                "Hızlı ve verimli hizmet.",
                "Personel çok yardımcıydı.",
                "İyileştirme için yer var.",
                "Yorum yok.",
            ],
            "vi": [
                "Dịch vụ xuất sắc, rất hài lòng!",
                "Trải nghiệm tốt nói chung.",
                "Có thể tốt hơn, có một số vấn đề.",
                "Không hài lòng với dịch vụ.",
                "Trải nghiệm trung bình, không có gì đặc biệt.",
                "Sẽ giới thiệu cho bạn bè.",
                "Dịch vụ nhanh và hiệu quả.",
                "Nhân viên rất hữu ích.",
                "Còn chỗ để cải thiện.",
                "Không có bình luận.",
            ],
        }

        # Generate random results
        for i in range(count):
            result = {}

            # Pick a random language for this response
            response_language = random.choice(locales) if locales else "en"

            for q in questions:
                qtype = q.get("type")
                name = q.get("name")

                if qtype == "radiogroup":
                    choices = [c["value"] for c in q.get("choices", [])]
                    if choices:
                        result[name] = random.choice(choices)

                elif qtype == "checkbox":
                    choices = [c["value"] for c in q.get("choices", [])]
                    max_choices = q.get("maxSelectedChoices", len(choices))
                    if choices:
                        num_selections = random.randint(
                            1, min(max_choices, len(choices))
                        )
                        result[name] = random.sample(choices, num_selections)

                elif qtype == "rating":
                    rate_min = q.get("rateMin", 1)
                    rate_max = q.get("rateMax", q.get("rateCount", 5))
                    result[name] = random.randint(rate_min, rate_max)

                elif qtype == "boolean":
                    result[name] = random.choice([True, False])

                elif qtype == "text":
                    if q.get("inputType") == "number":
                        min_val = q.get("min", 0)
                        max_val = q.get("max", 50)
                        result[name] = random.randint(min_val, max_val)
                    else:
                        result[name] = f"Demo text entry {i}"

                elif qtype == "comment":
                    # Use language-specific comments if available, fallback to English
                    comments = multilingual_comments.get(
                        response_language, multilingual_comments["en"]
                    )
                    result[name] = (
                        random.choice(comments) if random.random() > 0.3 else ""
                    )

            # Add language field for multilingual surveys
            if len(locales) > 1:
                result["language"] = response_language

            # Create result entry with random date within last 90 days
            days_ago = random.randint(0, 90)
            created = datetime.now(timezone.utc) - timedelta(days=days_ago)

            data = {
                "poll_id": str(uuid.uuid1()),
                "created": created,
                "user": "demo-user",
                "form_version": "demo",
                "result": result,
            }

            storage.store_result(survey, data)

    def _find_forms_dir(self) -> Path | None:
        """Return absolute path to the forms directory (scripts/forms)."""
        start = Path(__file__).resolve()
        for parent in start.parents:
            candidate = parent / "scripts" / "forms"
            if candidate.is_dir():
                return candidate
        cwd_candidate = Path.cwd() / "scripts" / "forms"
        if cwd_candidate.is_dir():
            return cwd_candidate
        return None

    def _load_prefilled_form_json(self):
        """Load prefilled.json form definition from scripts/forms."""
        forms_dir = self._find_forms_dir()
        if not forms_dir:
            return None
        prefilled_path = forms_dir / "prefilled.json"
        if not prefilled_path.is_file():
            return None
        try:
            import orjson

            return orjson.loads(prefilled_path.read_bytes())
        except Exception as e:
            logger.debug("Failed to load prefilled form JSON: %s", e)
            return None

    def _load_sample_addresses(self):
        """Load sample_address.json data from scripts/forms."""
        forms_dir = self._find_forms_dir()
        if not forms_dir:
            return []
        sample_path = forms_dir / "sample_address.json"
        if not sample_path.is_file():
            return []
        try:
            import orjson

            data = orjson.loads(sample_path.read_bytes())
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.debug("Failed to load sample addresses: %s", e)
            return []

    def _parse_iso_datetime(self, value):
        """Parse ISO datetime string to timezone-aware datetime."""
        if not value:
            return None
        try:
            if isinstance(value, str):
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            return value
        except Exception as e:
            logger.debug("Failed to parse ISO datetime: %s", e)
            return None

    def _create_prefilled_survey(self, container, user_id):
        """Create a prefilled address survey with demo results."""
        form_json = self._load_prefilled_form_json()
        if not form_json:
            return None, "prefilled.json not found"

        survey = plone.api.content.create(
            type="Survey",
            container=container,
            id="prefilled",
            title="Prefilled Address Book",
        )
        try:
            survey.language = "en"
            survey.reindexObject(idxs=["Language"])
        except Exception as e:
            logger.debug("Failed to set survey language: %s", e)
        try:
            survey.exclude_from_nav = True
            survey.reindexObject(idxs=["exclude_from_nav"])
        except Exception as e:
            logger.debug("Failed to exclude survey from nav: %s", e)
        try:
            survey.survey_languages = ["en"]
        except Exception as e:
            logger.debug("Failed to set survey languages: %s", e)
        try:
            survey.actions = {"store"}
        except Exception as e:
            logger.debug("Failed to set survey actions: %s", e)
        self._ensure_private(survey)

        annos = IAnnotations(survey)
        forms_service.save_form_version(
            annos,
            form_json,
            user_id,
            locked=False,
        )

        # Insert sample addresses as results
        sample_addresses = self._load_sample_addresses()
        if sample_addresses:
            results = annos.setdefault(RESULTS_KEY, OOBTree())
            seq_counter = Counter()
            for entry in sample_addresses:
                if not isinstance(entry, dict):
                    continue
                poll_id = str(uuid.uuid4())
                created = self._parse_iso_datetime(entry.get("created"))
                if not created:
                    created = datetime.now(timezone.utc)
                seq_no = seq_counter.increment()
                result_payload = dict(entry)
                if "created" not in result_payload:
                    result_payload["created"] = created.isoformat().replace(
                        "+00:00", "Z"
                    )
                results[poll_id] = {
                    "poll_id": poll_id,
                    "created": created,
                    "user": entry.get("user", ""),
                    "seq_no": seq_no,
                    "result": result_payload,
                }
            survey.seq_no = seq_counter

        return survey, None
