#!/usr/bin/env bash

OS_KERNEL=$(uname -s)
OS_VER=$(uname -v)
if  [[ ( $OS_KERNEL == "Linux" && $OS_VER == *"Microsoft"* ) ]]; then
    echo "Pre-commit hook needs git-bash to run.  It cannot run in the windows linux subsystem."
    echo "Add git bin directory to the front of your path variable, e.g:"
    echo "set PATH=C:\Program Files\Git\bin;%PATH%"
    exit 1
fi
if [[ "$(expr substr $OS_KERNEL 1 10)" == "MINGW64_NT" ]]; then
    POETRY_PATH=$(poetry.exe env info --path)
    source "$POETRY_PATH"\\Scripts\\activate
else
    source $(poetry env info --path)/bin/activate
fi
exec "$@"
