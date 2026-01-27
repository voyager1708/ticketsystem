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

# lint
RUN pip install --upgrade pip
RUN pip install flake8==6.0.0
COPY . /usr/src/app/
## flake8を実行すると、エラーになるので後で修正する
#RUN flake8 --ignore=E501,F401 .

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

# copy entrypoint.sh
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# create directory for the app user
RUN mkdir -p /home/app


# コンテナ内にホスト側と同じ UID/GID でグループ・ユーザーを作成
# GIDが空ならUIDを使う
RUN if [ -z "$GID" ]; then GID=$UID; fi \
 && addgroup --gid $GID $USERNAME \
 && adduser --uid $UID --gid $GID $USERNAME
 
# create the appropriate directories
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir $APP_HOME
WORKDIR $APP_HOME

# install dependencies
#RUN apt-get update && apt-get install -y --no-install-recommends netcat
COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /usr/src/app/requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache /wheels/*

# copy project
COPY . $APP_HOME

# chown all the files to the app user
RUN if [ -z "$GID" ]; then export GID=$UID; fi \
 && chown -R  ${USERNAME}:$GID $APP_HOME

# change to the app user
USER  ${USERNAME}


# run Django server!
ENTRYPOINT ["/entrypoint.sh"]

