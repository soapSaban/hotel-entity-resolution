docker run --rm -v '%cd%:/app' -w /app python:3.11-slim bash -c 'pip install -r pipeline_requirements.txt pytest && pytest tests/ -v'
