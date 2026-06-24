# Manufacturing Packing & Production Planning Tool

Desktop application for production planning, packing calculation and order management in panel manufacturing workflows.

## Overview

This project is a real-world desktop tool built to support daily manufacturing planning tasks.

It helps operators prepare production batches, calculate panel packs, manage order data and generate narrow 52 mm print output for production labels.

The public GitHub version contains no private company data, no service credentials and no production database. The SQLite database is created automatically on first launch.

## Features

- Manual production order input
- SQLite database storage
- Order save, open and replace workflow
- Top and bottom material fields
- Custom panels-per-pack setting
- Template packing mode for repeated packing patterns
- Roof panel mode with joint configuration
- Automatic pack calculation
- Current batch and completed batch preview
- 52 mm print output for narrow thermal labels
- English user interface
- Dark desktop UI inspired by Discord-style colors

## Tech Stack

- Python
- Tkinter
- SQLite
- HTML print output

## Packing Modes

The application supports two packing approaches:

### Custom Pack Size

The operator selects how many panels should be placed in each pack.

### Template Packing Mode

The application can also use predefined repeated packing patterns for regular and roof panel workflows.

## Database

The application creates a local SQLite database file automatically:

```text
hazit.db
```

The public repository does not include any real production database.

## Run on Windows

Double-click:

```text
run.bat
```

Or run manually:

```bash
python manufacturing_planning_tool.py
```

## My Role

I designed and developed this tool to automate repetitive manufacturing planning tasks, reduce manual calculation errors and improve daily production workflow.

## Security & Privacy Note

This is a cleaned portfolio version.

Private production data, real order history, service account files and internal company-specific files are not included.
