FROM python:3.11

ARG USERNAME
ARG UID
ENV USERNAME=${USERNAME:-python}
ENV UID=${UID:-1000}

LABEL org.label-schema.schema-version = "1.0"
LABEL org.label-schema.name "Umbrella IP Monitor"
LABEL org.label-schema.vendor "LearningToPi.com"
LABEL org.label-schema.description "Python service to check and update Umbrella network IP addressing."
LABEL org.label-schema.usage "/app/README.md"
LABEL org.label-schema.url = "https://www.learningtopi.com/python-modules-applications/umbrella_monitor/"
LABEL org.label-schema.vcs-url = "https://github.com/LearningToPi/umbrella_monitor"
LABEL org.label-schema.vcs-ref = "0965349"
LABEL org.label-schema.version = "1.0.1"
LABEL org.label-schema.release = "py3.11"
LABEL org.label-schema.architecture = "amd64"
LABEL org.label-schema.changelog-url = "https://github.com/LearningToPi/umbrella_monitor/blob/main/release_notes/v1.0.0.md"

LABEL org.label-schema.docker.cmd = 'docker run --name umbrella_monitor -v config.toml:/app/config.toml learningtopi/umbrella_monitor'
LABEL org.label-schema.docker.cmd.help = "docker run --rm -it learningtopi/umbrella_monitor --help"

EXPOSE 10025/tcp
WORKDIR /apps

RUN apt update && apt install net-tools -y && apt clean
RUN adduser --disabled-password --gecos '' $USERNAME -u $UID
RUN mkdir /app && chown $USERNAME:$USERNAME /app
USER $USERNAME:$USERNAME

ADD docker/requirements.txt /app
ADD docker/entrypoint.sh /app
ADD README.md /app
ENV PYTHONPATH="/app"
RUN pip3 install -r /app/requirements.txt


ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
