FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install flask requests fastmcp ansible

CMD ["python", "app.py"]
