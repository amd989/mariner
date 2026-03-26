# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mariner 2 is a web application for controlling MSLA 3D printers based on ChiTu controllers remotely. It consists of a Python Flask backend and a React TypeScript frontend that communicate via REST APIs.

## Architecture

- **Backend (`mariner/`)**: Flask application with file format parsers for various 3D printer formats (CTB, CBDDLP, FDG, Photon)
  - `mariner/server/app.py`: Main Flask application with WhiteNoise for static file serving
  - `mariner/server/api.py`: REST API endpoints for printer control and file management
  - `mariner/file_formats/`: Parsers for different printer file formats, including encrypted CTB files
  - `mariner/printer.py`: Printer communication interface
- **Frontend (`frontend/`)**: React/TypeScript SPA built with Vite
  - `frontend/src/lib/api.ts`: API client with TypeScript interfaces for backend communication
  - `frontend/src/pages/`: Page components (Index dashboard, Files manager)
  - `frontend/src/components/`: React components for print status, controls, file details, and UI
  - Tailwind CSS + shadcn/ui for styling, React Router for navigation, React Query for data fetching

## Development Commands

### Python Backend
```bash
# Install dependencies
poetry install

# Run the server
poetry run mariner

# Run tests
poetry run green

# Code formatting
poetry run black .

# Linting
poetry run flake8

# Type checking
poetry run pyre check
```

### Frontend
```bash
cd frontend/

# Install dependencies
npm install

# Development server (runs on :3000, proxies /api to Flask on :5050)
npm run dev

# Build for production
npm run build

# Run tests
npm test

# Linting
npm run lint
```

## Key Technical Details

- Python backend uses Poetry for dependency management (Python ^3.11)
- Frontend uses npm with Vite, Vitest for testing
- File format encryption/decryption handled in `mariner/file_formats/cipher.py` and `ctb_encrypted.py`
- Flask app serves frontend static files via WhiteNoise middleware
- CSRF protection enabled via Flask-WTF
- Printer communication via pyserial for ChiTu-based controllers

## Supported File Formats

The application can parse and preview multiple 3D printer file formats:
- `.ctb` (including encrypted variants)
- `.cbddlp`
- `.fdg`
- `.photon`

Each format has dedicated parser modules in `mariner/file_formats/` with corresponding test files.
