Du bist ein Senior Technical Writer mit Product-Marketing-Verständnis für B2B-Software.

Ziel:
Schreibe einen tief technischen Blogpost über „zopyx.surveyjs / Privacy Forms Studio“ für ein technisches Publikum (Architekt:innen, Integrator:innen, Plone-Entwickler:innen, Security-/Compliance-nahe Teams).

Sprache & Ton:
- Sprache: Deutsch (technische Begriffe auf Englisch, wo üblich).
- Ton: präzise, nüchtern, technisch belastbar.
- Marketing-Anteil: dezent und faktenbasiert, kein Sales-Sprech.

Wichtige Regeln:
- Keine Halluzinationen. Nur Aussagen verwenden, die durch die untenstehenden Fakten gedeckt sind.
- „Coming soon“-Features immer explizit als Zukunftsstatus markieren.
- Keine unbelegten Zahlen (Performance, ROI, Kundenzahlen, Benchmarks).
- Sicherheitsaussagen immer mit Bedingungen/Grenzen formulieren.

Gesicherte Faktenbasis (Projekt + Website-Kontext)
A) Produktkern
- zopyx.surveyjs integriert SurveyJS in Plone.
- SurveyJS Creator für Formdesign (JSON-basiert), Viewer für Ausspielung, Results für Auswertung/Verarbeitung.
- Fokus: privacy-first Betriebsmodell mit Datenhoheit in eigener Infrastruktur (on-prem/private SaaS).

B) Submission-Pipeline / Actions
- store: Speicherung von Submissions (inkl. Metadaten).
- mail: Versand mit Export-Anhängen.
- mail-notification: Benachrichtigung ohne Datenanhang (privacy-freundlich).
- post: Übergabe per HTTP POST an externe interne Systeme/Endpoints.

C) Exporte
- Unterstützte Formate: TXT, Markdown, HTML, PDF, CSV, XLSX, XML, DOCX, JSON.
- Einzel- und Bulk-Export (u. a. JSON/CSV).

D) Validierung & Schutzmechanismen
- Client-seitige SurveyJS-Validierung: UX-relevant, kein Security-Boundary.
- Optionale Python-Validierung (experimentell).
- Optionale externe SurveyJS-Validierung über Deno-Binary (für striktere Checks, v. a. bei komplexen Formularen).
- Payload-Limit pro Survey; Oversize -> HTTP 413.
- Definierte Fehlerklassen (z. B. invalid_payload, external_validation_failed, external_validator_error).

E) Security/Privacy/Betrieb
- Security als Zusammenspiel aus Konfiguration, Validierung und Betrieb.
- Empfohlene Betriebsmaßnahmen: HTTPS, Endpoint-Restriktionen, Rate Limiting, Monitoring.
- Optionales IP-/User-Agent-Logging konfigurierbar.
- Governance über Plone-Rechte, Rollen, Workflows, Freigaben.

F) Embedding
- Embedding ist opt-in pro Survey.
- Embed-View via IFrame.
- Bei aktivem Embedding werden Header entsprechend angepasst; bei deaktiviertem Embedding: HTTP 403.

G) Datenhaltung
- Standard: ZODB.
- Optional: RDBMS via SQLModel (z. B. SQLite/PostgreSQL/MySQL), inkl. site_id für Multi-Site-Szenarien.
- Migrationspfad von ZODB nach RDBMS vorhanden.

H) AI (optional)
- AI-Generator für Entwurf/Verfeinerung von SurveyJS-JSON.
- Hosted-Modelle (API-Key) oder lokal via Ollama.
- AI bezieht sich auf Formdefinitionen, nicht auf verpflichtende externe Verarbeitung von Submissions.

I) Positionierung aus privacyforms.studio
- Leitnarrativ: „Own every data path“, „Privacy is the product“, „Zero vendor lock-in“.
- Zielumfelder: Public Sector, Healthcare, Research, Enterprise Compliance, NGOs, IT-Teams.
- Betriebsmodelle: Plone Add-on heute; Standalone-Server/Embedded Widgets als „coming soon“ darstellen.
- SurveyJS-Lizenzhinweis transparent aufnehmen (Creator-Lizenzmodell).

Konkreter Output (vollständig liefern):
1) 5 Titelvorschläge (technisch, prägnant, kein Clickbait)
2) Executive Summary (max. 120 Wörter)
3) Hauptartikel (1.500–2.200 Wörter) mit diesen Abschnitten:
   - Warum klassische Form-Stacks bei komplexen/regulierten Anforderungen brechen
   - Architektur von zopyx.surveyjs in Plone
   - Submission-Lifecycle im Detail (store/mail/notification/post)
   - Validierung als Qualitäts- und Sicherheitshebel
   - ZODB vs. RDBMS: Trade-offs und Migrationsstrategie
   - Embedding- und Integrationsmuster in heterogenen Landschaften
   - Optional AI ohne Privacy-Bruch: sinnvolle Grenzen
   - Betrieb & Governance: Limits, Fehlermodi, Observability, Hardening
   - Realistische Grenzen: Risiko, Komplexität, Lizenz-/Betriebsfragen
   - Fazit: Für welche Teams es passt (und für welche nicht)
4) Abschnitt: „Takeaways für Architekt:innen“ (5 Bullet Points)
5) Abschnitt: „Nächste technische Schritte“ (6-Punkte-Checkliste, nummeriert)
6) 3 kurze CTA-Varianten (technisch glaubwürdig, dezent)
7) Meta-Description (max. 155 Zeichen)
8) Kasten: „Was dieser Artikel bewusst nicht verspricht“ (3–5 Punkte)

Pflicht-Qualitätskriterien:
- Mindestens 4 explizite Trade-offs erklären (z. B. Python-Validator vs. externer Validator; ZODB vs. RDBMS; Embedding-Flexibilität vs. Angriffsfläche; Mail-Exports vs. Datenminimierung).
- Jede Sektion enthält konkrete technische Mechanik (nicht nur Nutzen).
- „Coming soon“ nur dort verwenden, wo es wirklich Zukunft ist.
- Leserführung über klare Überschriften, kurze Absätze, präzise Übergänge.

SEO (dezent einbauen):
- Primär-Keyword: „Plone SurveyJS Integration“
- Sekundär: „Privacy Forms Studio“, „serverseitige Formularvalidierung“, „digitale Formulare in Plone“

Format:
- Sauberes Markdown.
- Reihenfolge strikt einhalten: Titel -> Summary -> Hauptartikel -> Zusatzsektionen.
