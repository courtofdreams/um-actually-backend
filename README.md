# Um Actually Backend

This is the backend service for the "Um Actually" application, which provides text analysis and fact-checking functionalities using OpenAI's language models.


## Installation
1. Please ensure you have Python 3.8+ and Poetry installed.
2. Clone the repository
3. Install dependencies:
```bash
poetry install
```

## Local Development
 Add your OpenAI API key to a `.env` file in the root directory:
```plaintext
OPENAI_API_KEY=your_openai_api_key_here
```
To start the development server locally, run:
```bash
sh start_dev_server.sh
```
or
```bash
uvicorn main:app --reload --env-file .env
``` 


## Directory Structure
```
um-actually-backend/
│── api/
│   └── routes/
│       └── text_analysis.py.    ## Text analysis API endpoints
│── schemas/                    ## models for request/response
│── services/
│   └── analysis_service.py    ## Analysis logic using OpenAI API
│   └── openai_service.py       ## OpenAI API wrapper
│── test/                    ## Unit and integration tests and input samples
│── main.py
│── pyproject.toml
│── README.md
└── ...


## Testing
To run tests, the text and youtube video on /demo folder.

## Deployment

### Initial Setup
```bash
# Install Fly CLI
brew install flyctl

# Login to Fly.io
flyctl auth login

# Update fly.toml line 8 with your app name
# Create app
flyctl apps create your-app-name

# Set OpenAI API key
flyctl secrets set OPENAI_API_KEY=your-openai-key

# Deploy
flyctl deploy
```

### CI/CD
GitHub Actions auto-deploys on push to `main`. Add secret in repo Settings → Secrets:
- `FLY_API_TOKEN` (get with `flyctl auth token`)

### Production Config
Update `main.py` line 17 CORS for production:
```python
origins = ["https://your-frontend-url.fly.dev", "http://localhost:3000"]
```