FROM python:3.14.9-slim

# Install git
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean

EXPOSE 5000

ENV FLASK_DEBUG=0

WORKDIR /opt/solrizer

# Copy project
# This all git tracked files will be copied, so that
# the version can be derived without any git diffs
COPY --exclude=.git . .

# Temporarily mount the .git folder to infer the version during installation
RUN --mount=source=.git,target=.git,type=bind \
    pip install -e ".[redis]"

VOLUME /var/cache/solrizer

ENTRYPOINT [ "solrizer" ]
