# Fixes missing imports using Ruff and RipGrep (CLI and import)

## Tested against Windows / Python 3.11 / Anaconda

## pip install ruffrgimportfixer

A Python script for adding missing import statements in your Python code.
The script utilizes ruff and ripgrep to identify missing imports and organizes them based on various criteria, including the number of errors, the total number of imports, and the length of the import line.

```python
Usage:
    from ruffrgimportfixer import fix_imports
	fix_imports('some_pythonfile.py')
	# or from the commandline ('some_pythonfile.py' as the only arg)
    
Dependencies:
    - ruff (https://github.com/astral-sh/ruff)
    - ripgrep (https://github.com/BurntSushi/ripgrep)
	# Both must be in sys.path
```
