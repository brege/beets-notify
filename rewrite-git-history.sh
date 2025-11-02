#!/bin/bash

# this script will rewrite the dummy nsmes and emails from
# a sloppy repo to your name, email, and gpg signature without
# changing the commit history (dates)

git filter-branch --env-filter '
OLD_EMAIL="notroot@beelink"
CORRECT_NAME="Wyatt Brege"
CORRECT_EMAIL="wyatt@brege.org"

if [ "$GIT_COMMITTER_EMAIL" = "$OLD_EMAIL" ]; then
    export GIT_COMMITTER_NAME="$CORRECT_NAME"
    export GIT_COMMITTER_EMAIL="$CORRECT_EMAIL"
fi
if [ "$GIT_AUTHOR_EMAIL" = "$OLD_EMAIL" ]; then
    export GIT_AUTHOR_NAME="$CORRECT_NAME"
    export GIT_AUTHOR_EMAIL="$CORRECT_EMAIL"
fi
' --commit-filter 'git commit-tree -S "$@"' -- --branches --tags


