#!/usr/bin/env bash
gunicorn -w 1 -b 0.0.0.0:$PORT api_flask:app
