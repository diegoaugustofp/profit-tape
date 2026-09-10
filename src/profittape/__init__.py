"""profit-tape — captura de tape e book da B3 via ProfitDLL."""

try:
    from ._version import __version__ as __version__  # gerado pelo hatch-vcs
except ImportError:
    # Rodando direto da arvore fonte sem instalar (raro; a maioria dos
    # caminhos do projeto usa `pip install -e` ou `pip install .`).
    __version__ = "0.0.0+sem-instalacao"
