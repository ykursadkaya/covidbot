FROM python:3.7-alpine

WORKDIR /src

COPY requirements.txt ./

RUN pip --no-cache-dir install -r requirements.txt

ENV TELEGRAM_API_TOKEN api_token
ENV TELEGRAM_CHAT_ID chat_id

COPY covidbot.py ./

EXPOSE 5000

ENTRYPOINT ["python", "covidbot.py"]
