"""ANTLR4 lexer/parser/listener for COBOL 85, generated from the ProLeap grammar.

Provenance
----------
``Cobol85.g4`` is the COBOL 85 grammar from the ProLeap COBOL parser
(https://github.com/uwol/proleap-cobol-parser), as mirrored in
antlr/grammars-v4. Copyright (C) Ulrich Wolffgang, MIT licensed.

The ``Cobol85Lexer.py`` / ``Cobol85Parser.py`` / ``Cobol85Listener.py``
modules are generated and should not be edited by hand. To regenerate::

    java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -listener -no-visitor \\
        -o . Cobol85.g4

(keep the ANTLR tool version in sync with the ``antlr4-python3-runtime``
version pinned in ``pyproject.toml``).
"""
