BRGSentimentbot Setup and Usage
==============================

Follow these steps to set up the bot and run it from scratch.

1. Clone the repository
   ```bash
   git clone https://github.com/<your-repo>/BRGSentimentbot.git
   cd BRGSentimentbot
   ```

2. Install dependencies (recommended: use a virtual environment)
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set your API keys
   ```bash
   export OPENAI_API_KEY="your_openai_key_here"
   export NEWSAPI_KEY="your_newsapi_key_here"
   # Windows PowerShell:
   # $env:OPENAI_API_KEY="your_openai_key_here"
   # $env:NEWSAPI_KEY="your_newsapi_key_here"
   ```

4. Run the bot
   ```bash
   python -m typer sentiment_bot.cli live  # continuous mode
   # or for a single run
   python -m typer sentiment_bot.cli once
   ```

5. Explore other modes
   ```bash
   python -m typer sentiment_bot.cli --help
   ```
