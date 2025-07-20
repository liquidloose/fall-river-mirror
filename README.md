# FastAPI, Docker, and WordPress dev environment for The Fall River Mirror


Use this command to reload the server from inside the container: 
`uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level info `

Here are the log levels:
1. debug: Shows the most detailed information, useful for development and troubleshooting
2. info: (Default) Shows general operational information
3. warning: Shows only warning and error messages
4. error: Shows only error messages
5. critical: Shows only critical error messages



