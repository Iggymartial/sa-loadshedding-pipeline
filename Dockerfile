# One shared image for all three pipeline stages (extract, transform,
# load). They already share almost every dependency (python-dotenv,
# pandas), so three separate images would mean three separate multi-hundred-MB
# builds for very little actual isolation benefit. Which SCRIPT runs is
# decided per-container via the `command:` override in docker-compose.yml,
# not baked into the image itself.
FROM python:3.13-slim

WORKDIR /app

# Install dependencies for all three stages up front, before copying any
# source code. Docker caches layers - as long as these requirements files
# don't change, this whole layer is reused on every rebuild, even if the
# actual Python code changes constantly. Ordering matters here.
COPY extractor/requirements.txt ./extractor-requirements.txt
COPY transform/requirements.txt ./transform-requirements.txt
COPY loader/requirements.txt ./loader-requirements.txt

RUN pip install --no-cache-dir \
    -r extractor-requirements.txt \
    -r transform-requirements.txt \
    -r loader-requirements.txt

# Now copy the actual pipeline code - this layer changes often, so it's
# deliberately placed AFTER the dependency install layer above.
COPY extractor/ ./extractor/
COPY transform/ ./transform/
COPY loader/ ./loader/

# No default CMD that actually does something - which script runs is
# always specified explicitly via docker-compose.yml's `command:` for
# each service. Running this image directly with no override just
# explains that, rather than silently doing nothing or crashing.
CMD ["python", "-c", "print('Specify a stage to run, e.g.: docker compose run --rm extractor')"]
