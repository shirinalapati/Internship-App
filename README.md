# Internship Matcher

A web application that scrapes major company job sites and intelligently matches them with user resumes, showing compatibility scores and detailed explanations.

## Features

- **Smart Resume Parsing**: Uses GPT-4o for accurate skill extraction with context awareness
- **Multi-Company Job Scraping**: Scrapes internship opportunities from major tech companies
- **Intelligent Matching**: Advanced matching algorithm that considers skills, experience, and requirements
- **Real-time Results**: Fast processing with detailed match explanations

## Recent Updates

### LLM-Only Skill Extraction
The system now uses **ONLY** OpenAI's GPT-4o for intelligent skill extraction from resumes:

- **Context Awareness**: Distinguishes between skills the user has vs. wants to learn
- **Zero Hallucination**: Only extracts skills with concrete evidence from the resume
- **No Regex Fallback**: Pure LLM-based extraction for maximum accuracy
- **JSON Structured Output**: Returns skills in a clean, structured format
- **Smart Error Handling**: Clear error messages for API key, quota, and other issues

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Copy `env_template.txt` to `.env` and fill in your credentials:
   ```bash
   cp env_template.txt .env
   ```
   
   Required variables:
   - `OPENAI_API_KEY`: **REQUIRED** - Your OpenAI API key for skill extraction (no fallback method)
   - `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET`: For OAuth (optional)

3. **Run the Application**:
   ```bash
   python app.py
   ```

## Testing

Test the LLM skill extraction:
```bash
python test_llm_skill_extraction.py
```

This will test various scenarios including negative contexts and edge cases with the new LLM-only flow.

**Important**: The system now requires a valid OpenAI API key to function. There is no regex fallback.
