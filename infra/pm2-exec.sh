#!/bin/sh
# Keep files created by supervised processes private.
umask 077
exec "$@"
