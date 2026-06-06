"""External integrations: mocked clients for eRaktKosh + ICMR RDRI, plus
hooks for real WhatsApp and LLM providers in later phases.
"""

from app.integrations import eraktkosh, icmr_rdri

__all__ = ["eraktkosh", "icmr_rdri"]
