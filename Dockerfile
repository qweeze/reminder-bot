FROM python:3.8-alpine

ARG TZ='Asia/Yekaterinburg'
ENV DEFAULT_TZ ${TZ}
RUN apk upgrade --update \
 && apk add -U tzdata \
 && cp /usr/share/zoneinfo/${DEFAULT_TZ} /etc/localtime \
 && apk del tzdata \
 && rm -rf /var/cache/apk/*

ADD reminder reminder
ADD main.py main.py
ENTRYPOINT ["python", "main.py"]
