#!/bin/bash
source $(poetry env info --path)/bin/activate
exec "$@"
