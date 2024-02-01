import subprocess
import shutil
import re
import os, sys
import tempfile
from collections import defaultdict
from pathlib import Path


errorcodes = ["F821"]


def touch(path: str) -> bool:
    # touch('f:\\dada\\baba\\caca\\myfile.html')
    # original: https://github.com/andrewp-as-is/touch.py (not working anymore)
    def _fullpath(path):
        return os.path.abspath(os.path.expanduser(path))

    def _mkdir(path):
        path = path.replace("\\", "/")
        if path.find("/") > 0 and not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

    def _utime(path):
        try:
            os.utime(path, None)
        except Exception:
            open(path, "a").close()

    def touch_(path):
        if path:
            path = _fullpath(path)
            _mkdir(path)
            _utime(path)

    try:
        touch_(path)
        return True
    except Exception as Fe:
        print(Fe)
        return False


def get_tmpfile(suffix=".bin"):
    tfp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    filename = tfp.name
    filename = os.path.normpath(filename)
    tfp.close()
    touch(filename)
    return filename


def fix_imports(file):
    if __file__ == file:
        return None
    p = subprocess.run([sys.executable, __file__, file], capture_output=True)
    return p


if __name__ == "__main__":
    # Check if ruff and rg executables are available
    ruffpath = shutil.which("ruff.exe")
    if not ruffpath:
        input(
            "ruff not found! Please install ruff https://github.com/astral-sh/ruff , put it in your path and restart the script"
        )
        sys.exit(1)
    rgpath = shutil.which("rg.exe")
    if not ruffpath:
        input(
            "ripgrep not found! Please install ripgrep https://github.com/BurntSushi/ripgrep , put it in your path and restart the script"
        )
        sys.exit(1)

    # Get the path of the Python interpreter
    interpreter_folder = str(Path(sys.executable).parent)

    # Set the file types and get the target file from command-line arguments
    filetypes = "py,pyx"
    file = sys.argv[1]
    file_path_object = Path(file)

    # Check if the specified file exists
    if not file_path_object.exists():
        print("File {file} does not exist")
        sys.exit(1)

    # Read the content of the target file
    with open(file, mode="r", encoding="utf-8") as f:
        filecontent = f.read()

    # Extract folder information and create temporary and backup filenames
    file_folder = str(file_path_object.parent)
    if file_folder == ".":
        file_folder = os.getcwd()
    purefile = file_path_object.name
    tmp_file = os.path.join(file_folder, "__" + purefile)
    backupfile = os.path.join(file_folder, purefile + ".bak")

    # Create regular expressions for errorcodes (F821 ...)
    errorcodesregex = re.compile("|".join([f"\\b{x}\\b" for x in errorcodes]))
    folders = [interpreter_folder]
    if interpreter_folder not in file_folder:
        folders.append(file_folder)

    p = subprocess.run([ruffpath, file], capture_output=True)
    stdoutrufffirstrun = p.stdout.decode("utf-8", "backslashreplace")
    stdout = stdoutrufffirstrun.splitlines()
    stdoutlist = [
        re.findall(r"""Undefined\s+name\s+`([^`]+)`""", x)
        for x in stdout
        if errorcodesregex.search(x)
    ]

    # Exit if no missing imports are found
    if not stdoutlist:
        sys.exit(0)

    # Collect missing imports
    missingimports = set()

    for x in stdoutlist:
        for y in x:
            missingimports.add(y)

    # Write regular expressions to the temporary file for ripgrep
    regexdict = {}
    regextmpfile = get_tmpfile(suffix=".tmp")
    with open(regextmpfile, mode="w", encoding="utf-8") as f:
        for x in missingimports:
            r1 = rf"^\s*\bimport\b\s+\b{x}\b\s*$"
            r2 = rf"^\s*\bfrom\b\s+[^\s]+\s+\bimport\s+\b{x}\b\s*$"
            r3 = rf"^\s*\bimport\b\s+[^\s]+\s+\bas\b\s+\b{x}\b\s*$"
            r4 = rf"^\s*\bfrom\b\s+[^\s]+\s+\bimport\b\s[^\s]+\s\bas\s+\b{x}\b\s*$"
            f.write(r1)
            f.write("\n")
            f.write(r2)
            f.write("\n")
            f.write(r3)
            f.write("\n")
            f.write(r4)
            f.write("\n")

            # to sort ripgrep results
            regexdict[x] = {
                "r1": re.compile(r1),
                "r2": re.compile(r2),
                "r3": re.compile(r3),
                "r4": re.compile(r4),
            }

    foundimportlinescounter = defaultdict(int)
    foundimportlines = []

    # Search for missing imports in specified folders using ripgrep
    for folder_to_search in folders:
        results = subprocess.run(
            [
                rgpath,
                "-f",
                regextmpfile,
                "-g",
                f"*.{{{filetypes}}}",
                "-o",
                "--no-line-number",
                "--multiline",
                "-I",
                "--trim",
                "--case-sensitive",
                "--color=never",
                "--no-messages",
                "--no-unicode",  # faster, but no special chars
                "--no-ignore",
                "-a",
                "--crlf",
            ],
            capture_output=True,
            cwd=folder_to_search,
            env=os.environ.copy(),
        )

        foundimportlines.extend(
            [
                re.sub(r"\s+", " ", q.strip())
                for q in results.stdout.decode("utf-8", "backslashreplace").splitlines()
            ]
        )

    # Continue processing only if import lines are found
    if not foundimportlines:
        sys.exit(0)

    # Count occurrences of each import line
    for importedline in foundimportlines:
        foundimportlinescounter[importedline] += 1

    # Identify unique import lines
    resultstdout = set(foundimportlines)
    foundpackagesdict = {}

    # Match import lines with regular expressions and organize results
    for resultline in resultstdout:
        for k, v in regexdict.items():
            if k not in foundpackagesdict:
                foundpackagesdict[k] = []
            for regexpr in v.items():
                resultregex = regexpr[1].findall(resultline)
                if resultregex:
                    foundpackagesdict[k].append(resultline)

    foundpackagesdict = {
        k: sorted(set(v), key=len) for k, v in foundpackagesdict.items()
    }

    # Extract the best import line for each package (fewest errors / most imports / shortest line)
    ruff_all_results_dict = {}
    for packagename, packageimportlines in foundpackagesdict.items():
        ruff_all_results = []
        ruff_all_results_dict[packagename] = []
        for packageimportline in packageimportlines:
            with open(tmp_file, mode="w", encoding="utf-8") as f:
                f.write(packageimportline)
                f.write("\n")
                f.write(filecontent)
            ptest = subprocess.run([ruffpath, tmp_file], capture_output=True)
            stdoutrufftestrun = ptest.stdout.decode("utf-8", "backslashreplace")
            ruff_all_results.append(
                [
                    len(stdoutrufftestrun.strip().splitlines()),
                    -foundimportlinescounter.get(packageimportline, -1),
                    len(packageimportline),
                    packagename,
                    packageimportline,
                ]
            )
            ruff_all_results_dict[packagename] = ruff_all_results

        if ruff_all_results_dict[packagename]:
            ruff_all_results_dict[packagename] = sorted(
                ruff_all_results_dict[packagename],
                key=lambda x: x[:3],  # fewest errors / most imports / shortest line
            )[0][-1]

    # Backup the original file content
    with open(backupfile, mode="w", encoding="utf-8") as f:
        f.write(filecontent)

    # Write the modified file with the optimized import lines
    with open(file, mode="w", encoding="utf-8") as f:
        for k, v in ruff_all_results_dict.items():
            if v:
                f.write(v)
                f.write("\n")
        f.write(filecontent)

    # Attempt to remove the temporary file
    try:
        os.remove(tmp_file)
    except Exception as e:
        print(e)
