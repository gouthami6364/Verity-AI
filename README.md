Verity AI

Verity AI is a privacy-focused AI chatbot designed to protect sensitive user information while providing a secure conversational experience.

The system detects personally identifiable information (PII) in user messages, redacts sensitive information before it is sent to the AI model, manages conversation context, monitors token usage and estimated costs, and provides security-related information through a system dashboard.

Features

AI-powered conversational chatbot

Automatic PII detection and redaction

Protection of sensitive information before it reaches the AI model

Context-aware conversations

Real-time token usage monitoring

Token usage percentage visualization

Estimated token cost tracking

AI-powered prompt refinement

Security warnings

Filter-change monitoring

PII protection dashboard

Responsive design for phone, tablet, and laptop

Secure backend API

Groq-powered AI responses

Privacy and Security

Privacy is one of the main goals of Verity AI.

Before a user's message is sent to the AI model, Verity AI checks the message for sensitive information.

The system can detect and protect information such as:

Email addresses

Phone numbers

Credit/debit card numbers

Aadhaar numbers

PAN numbers

Detected information is replaced with safe placeholders before the message is processed by the AI model.

Example

Original:

My email is example@gmail.com

Protected:

My email is [EMAIL REDACTED]

How Verity AI Works

User Message
      ↓
PII Detection
      ↓
PII Redaction
      ↓
Context Processing
      ↓
Token Analysis
      ↓
AI Model
      ↓
Secure Response

1. User Message

The user enters a message through the Verity AI web interface.

2. PII Detection

The backend analyzes the message for supported types of personally identifiable information.

3. PII Redaction

Sensitive information is replaced with protected placeholders.

4. Context Processing

The system manages conversation context so that previous safe conversation information can be used when generating responses.

5. Token Analysis

The system tracks token usage and estimates the associated cost.

6. AI Processing

The protected message is sent to the configured AI model through the Groq API.

7. Secure Response

The generated response is returned to the user through the Verity AI interface.

Dashboard

Verity AI includes a system dashboard that provides information about the current conversation and security processing.

The dashboard can display:

Context Lock

Shows the current conversation context being maintained by the system.

Token Usage

Displays the number of tokens being used and the percentage of the available context being consumed.

Token Cost

Displays the estimated cost associated with token usage.

PII Protection

Shows whether personally identifiable information was detected and protected.

Warnings

Displays security or processing warnings when applicable.

Filter Changes

Shows changes made by the protection and filtering system.

Refined Prompt

Provides an improved version of the user's prompt to help produce clearer AI responses.

Supported PII Detection

Verity AI currently supports detection and protection for:

PII Type

Description

EMAIL

Email addresses

PHONE

Phone numbers

CARD

Credit/debit card numbers

AADHAAR

Aadhaar numbers

PAN

PAN numbers

Credit/debit card numbers are additionally checked using validation logic before being treated as valid card information.

Prompt Refinement

Verity AI includes an AI-powered prompt refinement feature.

The system analyzes the protected version of the user's prompt and can generate a clearer or more structured version.

This helps users improve their prompts without exposing the original sensitive information unnecessarily.

The refined prompt can be reviewed through the dashboard before being used.

Token Monitoring

Verity AI monitors token usage during conversations.

The dashboard provides:

Current token usage

Maximum context capacity

Context usage percentage

Estimated token cost

The current configured context limit is:

131,072 tokens

Technologies Used

Frontend

HTML5

CSS3

JavaScript

Backend

Python

Flask

Gunicorn

AI

Groq API

OpenAI-compatible chat completion API

Security

Custom PII detection and redaction

Context management

Token tracking

Input filtering

Project Structure

Verity-AI/
│
├── server.py
├── pipeline.py
├── pii_redactor.py
├── contextlock.py
├── product_search.py
├── token_tracker.py
├── requirement.txt
├── index.html
│
├── static/
│   ├── style.css
│   └── script.js
│
└── README.md

File Description

server.py

The main Flask server.

It handles:

Web page serving

Chat requests

Prompt analysis

Backend API routes

Communication with the Verity AI pipeline

pipeline.py

Contains the main Verity AI processing pipeline.

It manages:

PII protection

Context handling

Token tracking

AI model communication

Conversation processing

Security information

pii_redactor.py

Responsible for detecting and redacting supported PII.

It protects information such as:

Email addresses

Phone numbers

Card numbers

Aadhaar numbers

PAN numbers

contextlock.py

Handles conversation context management.

token_tracker.py

Tracks token usage and estimated token costs.

product_search.py

Handles the application's product search functionality where applicable.

index.html

Contains the main Verity AI web interface.

static/style.css

Contains the application's visual design and responsive styling.

static/script.js

Handles frontend functionality including:

Sending messages

Receiving AI responses

Dashboard updates

PII status updates

Token meter updates

Prompt refinement

Product display

Installation

1. Clone the Repository

git clone https://github.com/gouthami6364/Verity-AI.git

cd Verity-AI

2. Create a Virtual Environment

Windows:

python -m venv venv
venv\Scripts\activate

macOS/Linux:

python -m venv venv
source venv/bin/activate

3. Install Dependencies

pip install -r requirement.txt

4. Configure the API Key

Verity AI uses the Groq API for AI model responses.

Create an environment variable named:

GROQ_API_KEY

Do not commit your API key to GitHub.

5. Run the Application

python server.py

The application will normally be available at:

http://127.0.0.1:5000

Environment Variables

Variable

Description

GROQ_API_KEY

API key used to communicate with Groq

GROQ_MODEL

AI model used by the application

If GROQ_MODEL is not provided, the application uses its configured default model.

Deployment

Verity AI can be deployed using a cloud hosting service such as Render.

Render Configuration

Build command:

pip install -r requirement.txt

Start command:

gunicorn server:app

Add the following environment variable in the Render dashboard:

GROQ_API_KEY

Security Considerations

Verity AI is designed to reduce exposure of sensitive information, but no software system can guarantee complete security.

Users should still avoid intentionally entering highly sensitive information unless necessary.

Important security practices include:

Never commit API keys to GitHub.

Store secrets using environment variables.

Keep dependencies updated.

Use HTTPS in production.

Avoid logging sensitive user information.

Keep production configuration separate from development configuration.

Privacy Approach

Verity AI follows a privacy-first processing approach.

Sensitive User Input
        ↓
Local PII Detection
        ↓
PII Redaction
        ↓
Protected Prompt
        ↓
AI Processing

This approach helps reduce the amount of sensitive information that is sent to the external AI service.

Responsive Design

The Verity AI interface is designed to work across different screen sizes.

Supported device categories include:

Mobile phones

Tablets

Laptops

Desktop computers

The interface automatically adjusts its layout based on the available screen size.

API Endpoints

GET /

Returns the main Verity AI web interface.

POST /chat

Processes a user message and returns the AI response together with security and token information.

POST /analyze

Analyzes and refines a protected user prompt.

Example Workflow

A user enters:

Please send the report to my email example@gmail.com

Verity AI detects the email address.

The protected message becomes:

Please send the report to my email [EMAIL REDACTED]

The protected message is then processed by the AI system.

The dashboard can indicate that PII was detected and protected.

Goals of the Project

The main goals of Verity AI are:

Protect sensitive user information.

Reduce unnecessary exposure of PII to AI systems.

Provide a secure conversational AI experience.

Give users visibility into token usage and processing.

Help users improve their prompts.

Provide security-related information through an easy-to-use dashboard.

Maintain a responsive and modern web interface.

Future Improvements

Possible future improvements include:

Additional PII detection types

More advanced privacy controls

Improved prompt security analysis

More detailed security logs

User authentication

Encrypted conversation storage

Additional AI model providers

Advanced token analytics

Improved context management

Additional deployment options

Disclaimer

Verity AI is a software project designed to demonstrate privacy-focused AI interaction and PII protection.

PII detection is based on pattern matching and validation logic and may not detect every possible form of sensitive information.

Users should not rely on the application as a complete replacement for professional security, privacy, or compliance systems.

License

This project is available for educational and development purposes.

Add your preferred license here if you choose to publish the project under an open-source license.

Author

Gouthami

GitHub:
https://github.com/gouthami6364/Verity-AI

Verity AI

Privacy First.
Secure Conversations.
Smarter AI Interaction.
