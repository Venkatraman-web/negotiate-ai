# 🤝 Negotiate AI

An AI-powered negotiation simulator that helps users practice and improve their negotiation skills through realistic, interactive conversations with an LLM-powered negotiation agent.

Unlike simple chatbots, Negotiate AI simulates dynamic negotiations by tracking negotiation state, evaluating user communication, adapting responses based on personality, and generating detailed performance feedback at the end of every session.

---

# 🚀 Features

- AI-powered negotiation partner
- Multiple negotiation scenarios
- Multiple AI personalities
- Dynamic negotiation engine
- Trust and patience tracking
- Real-time offer progression
- Multi-round negotiations
- Automatic negotiation report generation
- LLM-based communication evaluation
- Clean React frontend
- FastAPI backend
- Modular provider architecture for future LLM providers

---

# 🎯 Supported Scenarios

- 💼 Salary Negotiation
- 💻 Freelance Project


Each scenario provides its own negotiation context, objectives, and discussion topics.

---

# 🎭 AI Personalities

The AI negotiator can behave using different negotiation styles.

### 😊 Friendly

- Warm and respectful
- Encourages collaboration
- Makes reasonable concessions
- Builds rapport

---

### 😠 Aggressive

- Angry and impatient
- Pushes back strongly
- Makes very few concessions
- Challenges unrealistic demands
- Can terminate negotiations early

---

### 🧠 Logical

- Evidence-driven
- Fact-based reasoning
- Emotionally neutral
- Requests justification before conceding

---

### 🤝 Cooperative

- Focuses on win-win outcomes
- Suggests compromises
- Explores alternatives
- Keeps negotiations productive

---

### 🦈 Manipulative

- Uses strategic negotiation techniques
- Anchors offers
- Applies subtle psychological pressure
- Redirects conversations to strengthen its position

---

# 🏗️ System Architecture

```
Frontend (React)

        │

        ▼

FastAPI Backend

        │

        ├──────── Session Manager
        │
        ├──────── Negotiation Engine
        │
        ├──────── Prompt Builder
        │
        ├──────── LLM Service
        │
        ├──────── Message Analyzer
        │
        └──────── Report Generator

                    │

                    ▼

              Ollama (Llama 3.2)
```

The architecture separates business logic from LLM communication, making it easy to replace the model provider in the future.

---

# 🧩 Backend Modules

## Session Manager

Responsible for:

- Creating sessions
- Managing conversation history
- Tracking negotiation state
- Storing offers
- Tracking rounds

---

## Negotiation Engine

Responsible for:

- Updating trust
- Updating patience
- Processing offers
- Controlling negotiation flow
- Applying negotiation rules

---

## Prompt Builder

Builds prompts using:

- Scenario
- Personality
- Conversation history
- Current offer
- Trust
- Patience
- Round
- Negotiation status

The Prompt Builder is read-only and never modifies session data.

---

## LLM Service

Acts as the single communication layer between the backend and the language model.

Uses a provider abstraction:

```
BaseLLMProvider

        │

        ├── OllamaProvider
        ├── OpenAIProvider (future)
        ├── GeminiProvider (future)
        └── ClaudeProvider (future)
```

Only the provider needs to change when switching models.

---

## Message Analyzer

Analyzes user negotiation messages using the LLM.

Evaluates:

- Politeness
- Confidence
- Reasoning quality
- Aggression
- Flexibility

These metrics are used by the negotiation engine.

---

## Report Generator

After negotiation completion, generates a personalized report including:

- Overall score
- Communication evaluation
- Negotiation skills assessment
- Strengths
- Weaknesses
- Personalized improvement suggestions
- Overall performance summary

---

# 🖥️ Tech Stack

## Frontend

- React
- Vite
- Tailwind CSS
- Lucide Icons

---

## Backend

- FastAPI
- Python
- Pydantic

---

## AI

- Ollama
- Llama 3.2

---

# 📂 Project Structure

```
frontend/
│
├── src/
├── public/
└── package.json

backend/
│
├── core/
├── models/
├── routes/
├── services/
│   ├── negotiation_engine.py
│   ├── prompt_builder.py
│   ├── llm_service.py
│   ├── message_analyzer.py
│   └── report_generator.py
│
├── tests/
├── app.py
└── requirements.txt
```

---

# ⚙️ Installation

## Clone

```bash
git clone https://github.com/yourusername/negotiate-ai.git
```

---

## Backend

```bash
cd backend

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt
```

Run:

```bash
uvicorn app:app --reload
```

---

## Frontend

```bash
cd frontend

npm install

npm run dev
```

---

## Start Ollama

```bash
ollama run llama3.2
```

---

# 📸 Workflow

1. Select negotiation scenario
2. Select AI personality
3. Start negotiation
4. Negotiate across multiple rounds
5. Receive dynamic AI responses
6. Finish negotiation
7. View personalized performance report

---

# 🔮 Future Improvements

- OpenAI integration
- Claude integration
- Gemini integration
- Voice negotiation mode
- Speech-to-text
- Multiple negotiation difficulty levels
- Team negotiations
- Negotiation analytics dashboard
- Authentication
- Session history
- PDF report export

---

# 🎯 Learning Outcomes

This project demonstrates:

- Large Language Model integration
- Prompt engineering
- FastAPI backend development
- React frontend development
- Clean architecture
- Provider abstraction
- Stateful AI applications
- REST API development
- Modular software design
- AI-powered evaluation systems

---

# 📄 License

This project is intended for educational and portfolio purposes.
