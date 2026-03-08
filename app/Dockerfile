###########
# BUILDER #
###########

# pull official base image
FROM python:3.12-slim-bookworm as builder

# set work directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        build-essential \
        pkg-config

# install build tooling
RUN pip install --upgrade pip

# install python dependencies
COPY ./requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt


#########
# FINAL #
#########


# pull official base image
FROM python:3.12-slim-bookworm

ARG UID
ARG GID
ARG USERNAME
ARG NUM_WORKERS

# copy entrypoint.sh
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 変数の確認
RUN echo "####### UID=${UID} GID=${GID} USERNAME=${USERNAME} NUM_WORKERS=${NUM_WORKERS}"

# create directory for the app user
RUN mkdir -p /home/app


# コンテナ内にホスト側と同じ UID/GID でグループ・ユーザーを作成
# GIDが空ならUIDを使う
RUN if [ -z "$GID" ]; then GID=$UID; fi \
 && addgroup --gid $GID $USERNAME \
 && adduser --uid $UID --gid $GID $USERNAME
 
# create the appropriate directories（venv は開発時にボリュームマウント用）
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir $APP_HOME /home/app/venv
WORKDIR $APP_HOME

# install dependencies
#RUN apt-get update && apt-get install -y --no-install-recommends netcat
COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /usr/src/app/requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir /wheels/*
# Playwright を確実に導入（wheels のみだと依存で入らない場合があるため）
RUN pip install --no-cache-dir playwright>=1.40.0

# Playwright: システム依存と Chromium をインストール（チケット HTML → PNG 用）
ENV PLAYWRIGHT_BROWSERS_PATH=/home/app/.cache/ms-playwright
RUN python -m playwright install-deps \
 && python -m playwright install chromium \
 && mkdir -p /home/app/.cache \
 && chown -R ${USERNAME}:${USERNAME} /home/app/.cache

# copy project
COPY . $APP_HOME

# chown all the files to the app user（venv は開発時マウントで上書きされる）
RUN if [ -z "$GID" ]; then export GID=$UID; fi \
 && chown -R  ${USERNAME}:$GID $APP_HOME \
 && chown ${USERNAME}:${USERNAME} /home/app/venv

# change to the app user
USER  ${USERNAME}


# run Django server!
ENTRYPOINT ["/entrypoint.sh"]

