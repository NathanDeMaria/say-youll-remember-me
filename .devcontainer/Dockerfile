FROM python:3.13-bookworm

# For persisting bash history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" && echo $SNIPPET >> "/root/.bashrc"

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /usr/local/bin/

# Install into the container's python instead of a project .venv, so the
# devcontainer's interpreter path is stable for the editor.
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Is this a good way to add stuff on load?
# Not sure, but it's working
COPY profile.sh /root/profile.sh
RUN echo ". profile.sh" >> "/root/.bashrc"

COPY uv.lock ./
COPY pyproject.toml ./
