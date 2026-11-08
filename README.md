## Members
- Antipuesto, Lenie
- Caraballo, Lynn Jean
- Cabico, Joan Marie


DEVELOPMENT OF A WEB-BASED SKIN TYPE IDENTIFICATION AND SKINCARE ROUTINE RECOMMENDATION SYSTEM
BSIT Class Project Concept Paper

INTRODUCTION
Background of the Project
Taking care of the skin is important, but some people do not know their skin type or which skincare products are suitable for them. Different people may have oily, dry, normal, combination, or sensitive skin. Using products that are not suitable for their skin may cause irritation or other skin problems. Because of this, people may find it difficult to choose the right skincare products and follow a proper skincare routine.
To help address this problem, the proposed project will develop a web-based Skin Type Identification and Skincare Routine Recommendation System. The system will help users identify their skin type by answering questions about their skin condition. It will provide general skincare product suggestions and recommended routines based on the user's skin type, concerns, and goals. It will also include a routine planner where users will be able to organize and track their daily skincare activities. Through this system, users will have an easier way to understand their skin and manage their skincare routines.



Statement of the Problem or Project Objectives
The main objective of this project will be to develop and evaluate a web-based Skin Type Identification and Skincare Routine Recommendation System that will help users identify their skin type and choose suitable skincare routines.
Specifically, the project will aim to:
1.	Develop a skin analysis feature that will help users identify their skin type through a questionnaire about their skin condition.
2.	Provide skincare product suggestions based on the user's identified skin type, skin concerns, and skincare goals.
3.	Create a skincare routine planner that will help users organize their morning and evening skincare activities.
4.	Develop a user account and profile feature that will allow users to manage their personal information and view their saved skin analysis results.
5.	Provide an assessment history feature that will allow users to review and compare their previous skin analysis results.
6.	Conduct user testing to evaluate the system's ease of use, performance, and usefulness in helping users manage their skincare routines.



Significance of the Project
The proposed system will benefit the following groups:
•	Skincare Users: The system will help users understand their skin type and find general skincare suggestions that match their skin needs.
•	People New to Skincare: The system will provide simple information about skin types, skincare products, and daily routines.
•	Students and Young Adults: The system will help them learn basic skincare practices and organize their skincare activities.
•	Future Researchers and Students: The project will serve as a reference for those who will develop similar web-based systems related to skincare and personal care.

Alignment with Institutional Research Agenda and Sustainable Development Goals
Institutional Research Agenda Alignment
The project will support the institution's Information Technology research priority by using web technology to provide skincare information and personalized routine suggestions. It will demonstrate how a web-based system can help users access information and manage their daily activities more easily.


Sustainable Development Goals (SDGs)
•	SDG 3: Good Health and Well-Being. The project will support access to basic skincare information and encourage users to follow regular skincare routines. The system will provide general information and will not replace advice from qualified healthcare professionals.
•	SDG 9: Industry, Innovation, and Infrastructure. The project will use web technology to provide a digital tool for skin type identification and skincare routine planning.

SCOPE AND LIMITATIONS
System Scope and Technical Architecture
The proposed system will be a web-based application designed for people who want to understand their skin type and manage their skincare routines. Users will be able to access the system through a web browser on a computer or mobile device.
Component	Description and Coverage
Core Modules	User Registration and Login, Skin Analysis, Skincare Product Recommendations, Morning and Evening Routine Planner, Routine Progress Tracking, Assessment History, and User Profile Management.
Skin Analysis	The system will allow users to answer questions about their skin condition and identify a possible skin type, such as oily, dry, normal, combination, or sensitive.
Product Recommendations	The system will suggest skincare products based on the user's skin type, concerns, and skincare goals.
Routine Planner	Users will be able to view and organize their morning and evening skincare steps and track their progress.
Assessment History	The system will save previous skin analysis records and allow users to review and compare their results.
Technology Stack	The system will use Python and Django for backend development, MySQL for database management, and HTML, CSS, JavaScript, and Bootstrap for the user interface.
Target Users	People who want to learn about their skin type, explore skincare products, and organize their daily skincare routines.

Limitations
The proposed system will have the following limitations:
1.	The system will provide general skincare information and suggestions only. It will not diagnose skin diseases or replace professional medical advice.
2.	The accuracy of the skin type identification will depend on the information provided by the users and the methods supported by the system.
3.	The product recommendations will depend on the skincare product information available in the system.
4.	The system will not guarantee that a recommended product will work for every user because people may react differently to skincare ingredients.
5.	The system will not include online purchasing or payment processing for skincare products.
6.	The system will require an internet connection if it is hosted online. Access through a local computer or network will depend on the system's setup.



AI SKINCARE ASSISTANT (GEMINI LIVE API)

The project includes an optional AI assistant that holds a short voice or text conversation about the user's skin. It asks one question at a time, covers oiliness, dryness, flaking, shine, sensitivity, and breakouts, and then produces a structured estimate that is saved to the existing assessment history and used to refresh the user's routines.

The assistant is available from the sidebar and from the dashboard card "Talk to SkinSync AI" at /assistant/.

How it works
- The Django server creates a short-lived, single-use Gemini Live token. The Gemini API key never reaches the browser.
- Voice mode streams microphone audio directly to the Gemini Live API over a secure WebSocket and plays the spoken reply in the browser. A live transcript is shown on screen.
- Text mode sends messages to Django, which calls the Gemini text model on the server.
- When the conversation ends, Gemini returns a structured assessment. The result is stored in AssistantSession and copied into the existing SkinAnalysis and SkinProfile records so it appears in assessment history and recommendations.
- Primary skin types are Oily, Dry, Normal, Combination, or Uncertain. Sensitivity is stored separately as Low, Moderate, High, or Unknown. If the answers are insufficient or conflicting, the result stays Uncertain instead of forcing a classification.

Setup
1. Install dependencies:
   pip install -r requirements.txt
2. Copy .env.example to .env and add your Gemini API key:
   GEMINI_API_KEY=your-key-here
3. Apply migrations:
   python manage.py migrate
4. Start the development server:
   python manage.py runserver
5. Sign in and open /assistant/.

Configuration values in .env
- GEMINI_API_KEY: required server-side API key.
- GEMINI_LIVE_MODEL: Live voice model, default gemini-3.8-live.
- GEMINI_TEXT_MODEL: text and structured-analysis model, default gemini-3.8-flash.
- GEMINI_LIVE_VOICE: prebuilt voice name, default Aoede.
- GEMINI_ASSISTANT_MAX_SECONDS: maximum voice session length, default 840 seconds.

If the page shows that Gemini is not configured, confirm that .env exists next to manage.py, GEMINI_API_KEY is set, and the Django server was restarted after the change.

Tests
The assistant test suite uses mocked Gemini calls and does not require an API key:
   python manage.py test apps.assistant.tests

Notes and limitations
- Voice sessions require a modern browser with microphone support and an internet connection. Use headphones to reduce echo.
- Audio-only Live sessions have a time limit (about 15 minutes). The interface warns before the limit and offers to build a result from the conversation so far.
- Results are AI-generated estimates, not medical diagnoses. The assistant does not detect skin disease, does not invent user details, and does not provide calibrated confidence scores.
- Users should see a dermatologist for severe, painful, rapidly worsening, or persistent skin concerns.
- The assistant is a supplementary feature. The existing questionnaire, recommendations, routines, and assessment history continue to work independently.

