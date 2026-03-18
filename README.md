# JTCAM BibTeX Editing Tool

A Python tool for reformatting and enriching BibTeX files using Crossref and Unpaywall APIs.

**Author:** Vincent Acary  
**License:** GPLv3

## Overview

This tool automatically processes BibTeX files to:
- Find and verify DOIs using the Crossref API
- Identify open access resources via Unpaywall
- Add OAI (Open Access Initiative) URLs for freely available papers
- Validate entries against Crossref data
- Clean up LaTeX and HTML encoding issues
- Format author names consistently

## Features

### Core Functionality
- **DOI Resolution**: Finds verified DOIs for entries using Crossref
- **BibTeX Enrichment**: Fetches complete bibliographic data from Crossref
- **Open Access Detection**: Queries Unpaywall for OA status and URLs
- **Entry Validation**: Compares input entries against Crossref data
- **Duplicate Detection**: Removes entries with identical DOIs
- **LaTeX Cleaning**: Fixes common encoding issues

### Interactive Mode
When validation fails, the tool can prompt you with options:
- `[f]orce` - Force validation (use Crossref entry)
- `[s]kip` - Skip double-check (keep input entry)
- `[c]ontinue` - Continue without changes

Decisions are tracked and suggested as command-line options for future runs.

## Installation

### Requirements
```bash
pip install bibtexparser habanero unpywall joblib
```

### Optional
```bash
pip install requests  # For better HTTP handling
```

## Usage

### Basic Usage
```bash
python jtcam_bibtex_editing.py input.bib
```

### With Options
```bash
python jtcam_bibtex_editing.py \
    --verbose=2 \
    --max-entry=100 \
    --stop-on-bad-check \
    input.bib
```

### Using Saved Decisions
After interactive mode, use the suggested options:
```bash
python jtcam_bibtex_editing.py \
    --forced-valid-crossref-entry=entry1,entry2 \
    --skip-double-check=entry3,entry4 \
    input.bib
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--help` | Display help message |
| `--verbose=N` | Set verbosity (0=WARNING, 1=INFO, 2=DEBUG) |
| `--output-unpaywall-data` | Include full Unpaywall data in output |
| `--skip-double-check=ID1,ID2,...` | Skip validation for specific entries |
| `--forced-valid-crossref-entry=ID1,ID2,...` | Force validation for entries |
| `--stop-on-bad-check` | Interactive mode on validation failures |
| `--max-entry=N` | Process only first N entries |
| `--keep-entry=ID1,field1,ID2,field2,...` | Preserve specific fields from input |
| `--split-output` | Create individual .bib files per entry |

## Architecture

### API Client Classes

The tool uses three API client classes for external services:

#### 1. CrossrefClient
```python
from jtcam_bibtex_editing import CrossrefClient

client = CrossrefClient(mailto="your@email.com")

# Search by bibliographic info
response = client.query("Smith 2020 Machine Learning")

# Get BibTeX for a DOI
bibtex, json, status = client.get_bibtex("10.1000/example")
```

#### 2. UnpaywallClient
```python
from jtcam_bibtex_editing import UnpaywallClient

client = UnpaywallClient(email="your@email.com")

# Query by DOI
result, msg, status = client.query_by_doi("10.1000/example")

# Extract OAI URL
oai_url, status = client.extract_oai_url(result)

# Get repository info
host_type, institution = client.get_repository_info(result)
```

#### 3. DOIOrgClient
```python
from jtcam_bibtex_editing import DOIOrgClient

client = DOIOrgClient(timeout=30)

# Fetch from doi.org
bibtex, json, status = client.get_bibtex("10.1000/example")
```

### Processing Pipeline

```
1. Parse Input
   └── Load BibTeX file with bibtexparser
   
2. Crossref DOI Search
   └── Query Crossref by author + title + year
   └── Store found DOI in 'found_doi'
   
3. Fetch BibTeX Entries
   └── Get BibTeX from Crossref or doi.org
   └── Parse and validate format
   
4. Validate Entries
   └── Compare year, title, entry type
   └── Interactive mode (if enabled)
   └── Remove duplicates
   
5. Unpaywall Query
   └── Check OA status by DOI
   └── Extract OAI URLs
   └── Detect arXiv/HAL repositories
   
6. Build Output
   └── Merge Crossref + input data
   └── Add DOI and OAI tags
   └── Clean LaTeX encoding
   
7. Generate Reports
   └── Summary table of problematic entries
   └── Suggest command-line options
```

## Configuration

### Environment Variables
```bash
export CROSSREF_MAILTO="your@email.com"  # For polite pool
```

### Cache
The tool maintains a pickle cache (`*_cache.pickle`) to avoid re-querying:
- Automatically updated after each step
- Entries are invalidated if input changes
- Safe to delete to force re-query

## Error Handling

The tool implements comprehensive error handling:

### Retry Logic
- Exponential backoff for transient failures
- Automatic retry on connection errors
- Respects rate limits (429 responses)

### Custom Exceptions
- `CrossrefAPIError` - Crossref API failures
- `UnpaywallAPIError` - Unpaywall API failures
- `BibtexParseError` - Parsing errors
- `DOINotFoundError` - DOI not found

### Graceful Degradation
- Continues processing on API errors
- Falls back to input entry if fetch fails
- Logs warnings for failed entries

## Output Files

### Main Output
`input_edited.bib` - Processed BibTeX file with:
- Verified DOIs in `crossref_doi` field
- OAI URLs in `unpaywalloaiurl` field
- Clean LaTeX encoding

### Split Output (with `--split-output`)
- `splitted_bibtex_entries/` - Directory with one .bib per entry
- `splitted_bib_entries.tex` - LaTeX input file listing all entries

### Cache
- `input_cache.pickle` - Cached query results

## Troubleshooting

### Rate Limiting
If you hit rate limits:
1. Use `--max-entry` to process in batches
2. Wait and retry (cache will be used)
3. Consider using `--skip-double-check` for known entries

### Validation Failures
Use `--stop-on-bad-check` to interactively handle mismatches:
- Often due to preprints vs. published versions
- Conference vs. journal versions
- Title differences (special characters)

### Pickle Errors
If cache becomes corrupted:
```bash
rm *_cache.pickle
```

## Development

### Project Structure
```
.
├── jtcam_bibtex_editing.py  # Main script
├── REFACTORING.md           # Refactoring suggestions
├── README.md                # This file
└── test/                    # Test directory
```

### Key Classes
- `Config` - Command-line configuration
- `EntryStore` - Typed storage for entry state
- `BibtexProcessor` - Main processing pipeline
- `InteractiveDecisions` - Track user choices

### Logging
Use Python's standard logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## References

- [Crossref API](https://api.crossref.org/)
- [Unpaywall API](https://unpaywall.org/products/api)
- [bibtexparser](https://bibtexparser.readthedocs.io/)
- [habanero](https://habanero.readthedocs.io/)

## Changelog

### Recent Changes
- Added API client classes (CrossrefClient, UnpaywallClient, DOIOrgClient)
- Implemented proper Python logging
- Added retry logic with exponential backoff
- Fixed parallel processing pickling issues
- Added interactive mode with decision tracking
- Improved error handling with custom exceptions

## License

GPLv3 - See LICENSE file for details
