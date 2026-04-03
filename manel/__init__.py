__version__ = "0.1.0"


def __getattr__(name):
    if name == "MangaTransformerPipeline":
        from manel.cli import MangaTransformerPipeline

        return MangaTransformerPipeline
    if name == "main":
        from manel.cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["MangaTransformerPipeline", "main"]
