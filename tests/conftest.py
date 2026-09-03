from pydantic_ai import models

# A unit test must opt into a fake model explicitly; accidental network calls fail fast.
models.ALLOW_MODEL_REQUESTS = False
