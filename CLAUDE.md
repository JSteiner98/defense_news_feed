# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## User Context

Beginner/intermediate Python developer transitioning into defense tech.
Prefer clear explanations of new patterns and the "why" behind code changes.

## Project Overview

Defense Brief is an automated news aggregator that scans RSS feeds, scores articles using the Gemini AI API, and emails a filtered daily digest focused on maritime defense, defense tech ("American Dynamism"), and geopolitics.

## Commands

```bash
# Activate the virtual environment (required before running anything)
source venv/bin/activate

# Run the main aggregator (fetches feeds, scores via Gemini, emails digest)
python main.py

# List available Gemini models (API connectivity test)
python list_models_v2.py
```

There is no test suite, linter, or build system configured yet.

## Architecture

**`main.py`** - Single-file pipeline with three stages:
1. **Fetch**: Pulls RSS entries via `feedparser` from `rss_urls` list (currently War on the Rocks only).
2. **Score**: Sends each article title+snippet to Gemini (`gemini-flash-latest`) with a prompt requesting JSON back (`score`, `summary`, `category`). Articles scoring >= 7/10 are kept.
3. **Email**: Formats surviving articles as HTML and sends via Gmail SMTP.

**`list_models_v2.py`** - Standalone utility that lists available Gemini models. Used to verify API key and connectivity.

## Environment Variables (`.env`)

Required keys loaded via `python-dotenv`:
- `GEMINI_API_KEY` - Google Gemini API key
- `EMAIL_ADDRESS` - Gmail address (sender and recipient)
- `EMAIL_PASSWORD` - Gmail app password for SMTP

## Key Dependencies

- `google-genai` - Gemini AI client (not the older `google-generativeai` package)
- `feedparser` - RSS/Atom feed parsing
- `python-dotenv` - `.env` file loading
- `pydantic` - Installed but not yet used; intended for data validation

## Coding Conventions

- Use type hints on all function signatures.
- Use Pydantic for data validation when adding new data models.
- When explaining code changes, include the "why" — the user is building Python proficiency.
- Always check `.gitignore` before creating new files or directories.

## Roadmap Context

Planned next steps: expand `rss_urls` with additional maritime/defense feeds (gCaptain, Maritime Executive), refine keyword filtering (Sealift, Anduril, Maritime Autonomy, MSC, Jones Act), and add Claude API summarization alongside or replacing Gemini.
