from app.services.knowledge_base import BaseKnowledgePlugin

_plugins: list[BaseKnowledgePlugin] = []


def register_plugin(plugin: BaseKnowledgePlugin) -> None:
    """Register a knowledge plugin. Idempotent — skips if already registered."""
    if any(p.name == plugin.name for p in _plugins):
        return
    _plugins.append(plugin)


def get_plugins() -> list[BaseKnowledgePlugin]:
    """Return all registered knowledge plugins."""
    return list(_plugins)
