import pkgutil
import importlib
from pathlib import Path

__all__ = []

__path__ = [str(Path(__file__).parent)]

for loader, module_name, is_pkg in pkgutil.iter_modules(__path__):
    if module_name == "__init__":
        continue

    _module = importlib.import_module(f'.{module_name}', package=__name__)

    if module_name not in __all__:
        __all__.append(module_name)

    for name in dir(_module):
        if not name.startswith('_'):
            obj = getattr(_module, name)
            globals()[name] = obj

            if name not in __all__:
                __all__.append(name)