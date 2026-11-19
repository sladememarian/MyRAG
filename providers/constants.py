"""Fixed provider metadata shared by settings, the admin and the LLM client.

Only these providers are supported. Their API roots are constants rather
than editable database fields so an admin cannot point the answering pipeline at
an arbitrary host (which would be a server-side request forgery risk). The
values can still be overridden for a deployment through environment variables.
"""

OPENROUTER = "openrouter"
ITERACOMPUTE = "iteracompute"
TOKENHARBOR = "tokenharbor"
ORCAROUTER = "orcarouter"

PROVIDER_CHOICES = (
    (OPENROUTER, "OpenRouter"),
    (ITERACOMPUTE, "Itera Compute"),
    (TOKENHARBOR, "Token Harbor"),
    (ORCAROUTER, "Orca Router"),
)

PROVIDER_NAMES = dict(PROVIDER_CHOICES)

DEFAULT_BASE_URLS = {
    OPENROUTER: "https://openrouter.ai/api/v1",
    ITERACOMPUTE: "https://api.iteracompute.com/v1",
    TOKENHARBOR: "https://tokenharbor.ai/v1",
    ORCAROUTER: "https://api.orcarouter.ai/v1",
}

DEFAULT_MODELS = {
    OPENROUTER: "inclusionai/ling-3.2-flash:free",
    ITERACOMPUTE: "Auto",
    TOKENHARBOR: "",
    ORCAROUTER: "orcarouter/free",
}

# Environment variable that holds a fallback key for each provider. A key added
# in the admin takes precedence; this one keeps a fresh checkout working.
API_KEY_ENV = {
    OPENROUTER: "OPENROUTER_API_KEY",
    ITERACOMPUTE: "ITERACOMPUTE_API_KEY",
    TOKENHARBOR: "TOKENHARBOR_API_KEY",
    ORCAROUTER: "ORCAROUTER_API_KEY",
}

BASE_URL_ENV = {
    OPENROUTER: "OPENROUTER_BASE_URL",
    ITERACOMPUTE: "ITERACOMPUTE_BASE_URL",
    TOKENHARBOR: "TOKENHARBOR_BASE_URL",
    ORCAROUTER: "ORCAROUTER_BASE_URL",
}

MODEL_ENV = {
    OPENROUTER: "OPENROUTER_MODEL",
    ITERACOMPUTE: "ITERACOMPUTE_MODEL",
    TOKENHARBOR: "TOKENHARBOR_MODEL",
    ORCAROUTER: "ORCAROUTER_MODEL",
}
