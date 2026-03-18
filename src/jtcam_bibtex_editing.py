#!/usr/bin/env python3
"""
JTCAM BibTeX Editing Tool

This script uses the Crossref and Unpaywall APIs to reformat author BibTeX files,
adding verified DOIs and OAI URLs for open access resources.

Copyright (C) 2022 Vincent Acary

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import getopt
import sys
import os
import pprint
import time
import json
import urllib  # For URL encoding compliant with LaTeX
import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum

# BibTeX parsing imports
from bibtexparser import load, dumps
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase, as_text


# =============================================================================
# Constants
# =============================================================================

class StoreKeys:
    """Constants for store dictionary keys."""
    INPUT = 'input'
    FOUND_DOI = 'found_doi'
    FOUND_DOI_STATUS = 'found_doi_status'
    CROSSREF_QUERY_STATUS = 'crossref_query_status'
    CROSSREF_BIBTEX_ENTRY = 'crossref_bibtex_entry'
    CROSSREF_BIBTEX_ENTRY_KEY = 'crossref_bibtex_entry_key'
    CROSSREF_JSON_ENTRY = 'crossref_json_entry'
    DOI_TO_BIBTEX_STATUS = 'doi_to_bibtex_status'
    UNPAYWALL_MSG = 'unpaywall_msg'
    UNPAYWALL_STATUS = 'unpaywall_status'
    UNPAYWALL_DATA = 'unpaywall_data'
    OAI_URL = 'oai_url'
    OAI_TYPE = 'oai_type'
    OAI_URL_FOR_LANDING_PAGE = 'oai_url_for_landing_page'
    CHECK = 'check'
    ACTION = 'action'
    OUTPUT_BIBTEX_ENTRY = 'output_bibtex_entry'
    DUPLICATE = 'duplicate'


class ValidationStatus(Enum):
    """Validation status values."""
    VALID = 'valid'
    INVALID = '!valid'
    SKIPPED = 'skipped'
    FAILED = 'failed'


# =============================================================================
# Dataclasses for Type Safety
# =============================================================================

@dataclass
class Timer:
    """Simple timer class for measuring execution time."""
    _start_time: Optional[float] = None
    
    def start(self) -> None:
        """Start the timer."""
        if self._start_time is not None:
            raise RuntimeError("Timer is running. Use .stop() to stop it")
        self._start_time = time.perf_counter()
    
    def stop(self) -> float:
        """Stop the timer and return elapsed time."""
        if self._start_time is None:
            raise RuntimeError("Timer is not running. Use .start() to start it")
        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")
        return elapsed_time


@dataclass
class EntryStore:
    """
    Typed storage for a single BibTeX entry's processing state.
    
    This replaces the untyped dictionary store[key] access with a dataclass
    that provides type safety and IDE autocomplete support.
    """
    # Required fields
    input: Dict[str, Any]
    
    # Crossref DOI search results
    found_doi: Optional[str] = None
    found_doi_status: Optional[str] = None
    crossref_query_status: Optional[str] = None
    
    # BibTeX entry from Crossref
    crossref_bibtex_entry: Optional[Dict[str, Any]] = None
    crossref_bibtex_entry_key: Optional[str] = None
    crossref_json_entry: Optional[str] = None
    doi_to_bibtex_status: Optional[str] = None
    
    # Unpaywall results
    unpaywall_msg: Optional[str] = None
    unpaywall_status: List[str] = field(default_factory=list)
    unpaywall_data: Optional[str] = None
    oai_url: Optional[str] = None
    oai_type: Optional[str] = None
    oai_url_for_landing_page: Optional[str] = None
    
    # Validation and output
    check: Optional[str] = None
    action: List[str] = field(default_factory=lambda: ['', ''])
    output_bibtex_entry: Optional[Dict[str, Any]] = None
    duplicate: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for pickle serialization."""
        return {
            StoreKeys.INPUT: self.input,
            StoreKeys.FOUND_DOI: self.found_doi,
            StoreKeys.FOUND_DOI_STATUS: self.found_doi_status,
            StoreKeys.CROSSREF_QUERY_STATUS: self.crossref_query_status,
            StoreKeys.CROSSREF_BIBTEX_ENTRY: self.crossref_bibtex_entry,
            StoreKeys.CROSSREF_BIBTEX_ENTRY_KEY: self.crossref_bibtex_entry_key,
            StoreKeys.CROSSREF_JSON_ENTRY: self.crossref_json_entry,
            StoreKeys.DOI_TO_BIBTEX_STATUS: self.doi_to_bibtex_status,
            StoreKeys.UNPAYWALL_MSG: self.unpaywall_msg,
            StoreKeys.UNPAYWALL_STATUS: self.unpaywall_status,
            StoreKeys.UNPAYWALL_DATA: self.unpaywall_data,
            StoreKeys.OAI_URL: self.oai_url,
            StoreKeys.OAI_TYPE: self.oai_type,
            StoreKeys.OAI_URL_FOR_LANDING_PAGE: self.oai_url_for_landing_page,
            StoreKeys.CHECK: self.check,
            StoreKeys.ACTION: self.action,
            StoreKeys.OUTPUT_BIBTEX_ENTRY: self.output_bibtex_entry,
            StoreKeys.DUPLICATE: self.duplicate,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EntryStore:
        """Create from dictionary (for pickle deserialization)."""
        return cls(
            input=data.get(StoreKeys.INPUT, {}),
            found_doi=data.get(StoreKeys.FOUND_DOI),
            found_doi_status=data.get(StoreKeys.FOUND_DOI_STATUS),
            crossref_query_status=data.get(StoreKeys.CROSSREF_QUERY_STATUS),
            crossref_bibtex_entry=data.get(StoreKeys.CROSSREF_BIBTEX_ENTRY),
            crossref_bibtex_entry_key=data.get(StoreKeys.CROSSREF_BIBTEX_ENTRY_KEY),
            crossref_json_entry=data.get(StoreKeys.CROSSREF_JSON_ENTRY),
            doi_to_bibtex_status=data.get(StoreKeys.DOI_TO_BIBTEX_STATUS),
            unpaywall_msg=data.get(StoreKeys.UNPAYWALL_MSG),
            unpaywall_status=data.get(StoreKeys.UNPAYWALL_STATUS, []),
            unpaywall_data=data.get(StoreKeys.UNPAYWALL_DATA),
            oai_url=data.get(StoreKeys.OAI_URL),
            oai_type=data.get(StoreKeys.OAI_TYPE),
            oai_url_for_landing_page=data.get(StoreKeys.OAI_URL_FOR_LANDING_PAGE),
            check=data.get(StoreKeys.CHECK),
            action=data.get(StoreKeys.ACTION, ['', '']),
            output_bibtex_entry=data.get(StoreKeys.OUTPUT_BIBTEX_ENTRY),
            duplicate=data.get(StoreKeys.DUPLICATE, False),
        )


@dataclass
class Config:
    """
    Configuration options for the BibTeX processor.
    
    Replaces the global `opts` variable with a typed dataclass
    that can be passed to functions explicitly.
    """
    filename: Optional[str] = None
    verbose: int = 0
    number_of_parallel_request: int = 2
    output_unpaywall_data: bool = False
    skip_double_check: List[str] = field(default_factory=list)
    forced_valid_crossref_entry: List[str] = field(default_factory=list)
    stop_on_bad_check: bool = False
    max_entry: int = 100000
    crossref_search_key: List[str] = field(default_factory=lambda: ['author', 'year', 'title'])
    use_input_doi: bool = True
    keep_entry: List[str] = field(default_factory=list)
    split_output: bool = False
    
    @classmethod
    def from_command_line(cls, argv: List[str]) -> Config:
        """Parse command line arguments and return Config instance."""
        config = cls()
        
        try:
            opts, args = getopt.gnu_getopt(
                argv[1:], '',
                ['help', 'verbose=', 'is-oa',
                 'output-unpaywall-data', 'skip-double-check=',
                 'forced-valid-crossref-entry=',
                 'stop-on-bad-check', 'max-entry=', 'keep-entry=',
                 'split-output'])
            
            for o, a in opts:
                if o == '--help':
                    config.usage(long=True)
                    exit(0)
                elif o == '--verbose':
                    config.verbose = int(a)
                elif o == '--output-unpaywall-data':
                    config.output_unpaywall_data = True
                elif o == '--skip-double-check':
                    config.skip_double_check = a.split(',')
                elif o == '--forced-valid-crossref-entry':
                    config.forced_valid_crossref_entry = a.split(',')
                elif o == '--stop-on-bad-check':
                    config.stop_on_bad_check = True
                elif o == '--max-entry':
                    config.max_entry = int(a)
                elif o == '--keep-entry':
                    config.keep_entry = a.split(',')
                elif o == '--split-output':
                    config.split_output = True
            
            if len(args) > 0:
                config.filename = args[0]
            else:
                config.usage()
                exit(1)
                
        except getopt.GetoptError as err:
            sys.stderr.write(f'{err}\n')
            config.usage()
            exit(2)
        
        return config
    
    def usage(self, long: bool = False) -> None:
        """Print usage information."""
        print(f'Usage: {os.path.split(sys.argv[0])[1]} [OPTION]... <bib file>')
        print()
        if not long:
            print("""[--help][--verbose][--output-unpaywall-data][--skip-double-check=][--stop-on-bad-check][--max-entry=][--keep-entry=][--forced-valid-crossref-entry=]
            """)
        else:
            print("""Options:
     --help
       display this message
     --verbose=
       set verbose level
     --output-unpaywall-data
       output the whole unpaywall data in the output bibtex file. Useful for checking query.
     --skip-double-check=<entry_id>,<entry_id>,...
       skip double check due to a mismatch between doi and bibtex info
     --forced-valid-crossref-entry=<entry_id>,<entry_id>,...
       forced the crossref entry to be valid and used
       some key can be kept from the author entry with --keep-entry
     --stop-on-bad-check
       stop (input()) on bad check to get info and hints
     --max-entry=<int>
       process only the first <int> max entries
     --keep-entry=<list of tuple>
            ex: [('toto1', 'author'), ('toto2', 'journal')]
       keep the key in entry of the input file. This can be used if the bibtex entry returned
            by crossref is bad.
     --split-output
       split output in multiple bib files to test entries one by one

     """)


# =============================================================================
# Logging
# =============================================================================

class Logger:
    """
    Simple logging class to replace global verbose_level.
    
    Can be extended to use Python's logging module.
    """
    
    def __init__(self, verbose: int = 1):
        self.verbose = verbose
        self.prefix = '[jtcam_bibtex_editing]'
    
    def log(self, *args: Any, **kwargs: Any) -> None:
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(self.prefix, *args, **kwargs)
    
    def debug(self, *args: Any, **kwargs: Any) -> None:
        """Print debug message (verbose >= 2)."""
        if self.verbose >= 2:
            print(f'{self.prefix} [DEBUG]', *args, **kwargs)
    
    def info(self, *args: Any, **kwargs: Any) -> None:
        """Print info message (verbose >= 1)."""
        if self.verbose >= 1:
            print(f'{self.prefix} [INFO]', *args, **kwargs)
    
    def warning(self, *args: Any, **kwargs: Any) -> None:
        """Print warning message (always)."""
        print(f'{self.prefix} [WARNING]', *args, **kwargs)


# =============================================================================
# Parallel processing
# =============================================================================
from joblib import Parallel, delayed


# =============================================================================
# Crossref API functions
# =============================================================================
from habanero import Crossref
from habanero import cn

# Set a mailto address to get into the "polite pool" (higher rate limits)
Crossref(mailto="jtcam@episciences.org")


def crossref_query(bibliographic: str, logger: Logger) -> Dict[str, Any]:
    """
    Query Crossref API for a bibliographic entry.
    
    Args:
        bibliographic: Search query string (author, title, year, etc.)
        logger: Logger instance for output
        
    Returns:
        dict: Crossref API response
    """
    logger.log(f'crossref query search starts on {bibliographic[:40]:40.40}...')
    cr = Crossref(
        base_url="https://api.crossref.org",
        mailto="jtcam@episciences.org"
    )

    try:
        x = cr.works(query_bibliographic=bibliographic, limit=1)
    except Exception as e:
        x = {'status': 'bad'}
        logger.log(f'exception is : {e}')

    logger.log(f'crossref query search ends on {bibliographic[:40]:40.40} with status {x["status"]}')
    return x


def crossref_get_doi_from_query_results(x: Dict[str, Any]) -> Optional[str]:
    """
    Extract DOI from Crossref query results.
    
    Args:
        x: Crossref API response
        
    Returns:
        DOI string or None if not found
    """
    try:
        doi = x['message']['items'][0]['DOI']
    except (KeyError, IndexError) as e:
        print(f'result from crossref has no DOI!! {e}')
        doi = None
    return doi


def bibtex_entries_to_crossref_dois(
    store: Dict[str, EntryStore],
    config: Config,
    logger: Logger
) -> None:
    """
    Search for DOIs for all BibTeX entries using Crossref.
    
    Args:
        store: Dictionary of EntryStore instances
        config: Configuration options
        logger: Logger instance
    """
    logger.log('Crossref doi search from bibtex input entry')
    bibliographic: Dict[str, Tuple[Dict[str, Any], str]] = {}
    
    for key, entry_store in store.items():
        entry = entry_store.input
        entry_id = entry.get('ID')
        
        if config.use_input_doi and entry.get('doi'):
            # Use existing doi from input, skip search
            logger.log(f'    use user input doi for {entry_id}')
            entry_store.crossref_query_status = 'ok'
            entry_store.found_doi = entry.get('doi')
        else:
            if entry_store.crossref_query_status != 'ok':
                query_text = ' '.join(
                    entry.get(k, '') for k in config.crossref_search_key
                )
                bibliographic[entry_id] = (entry, query_text)
            else:
                logger.log(f'    use cache entry for {entry_id}')
    
    if len(bibliographic) > 0:
        timer = Timer()
        timer.start()
        n_jobs = min(len(bibliographic), config.number_of_parallel_request)
        results = Parallel(n_jobs=n_jobs)(
            delayed(crossref_query)(bib[1], logger)
            for bib in bibliographic.values()
        )
        timer.stop()

        for (entry_id, (entry, _)), result in zip(bibliographic.items(), results):
            if result['status'] == 'ok':
                doi = crossref_get_doi_from_query_results(result)
                if doi is not None:
                    store[entry_id].found_doi = doi
                    store[entry_id].crossref_query_status = result['status']
                else:
                    store[entry_id].crossref_query_status = 'bad'


doi_to_bibtex_entry_server = 'doi.org'


def doi_to_crossref_bibtex_entry(doi: str, logger: Logger) -> Tuple[Optional[str], Optional[str], str]:
    """
    Get BibTeX entry from DOI using Crossref content negotiation.
    
    Args:
        doi: DOI string
        logger: Logger instance
        
    Returns:
        Tuple of (bibtex_entry_str, json_entry, status)
    """
    cr = Crossref(mailto="jtcam@episciences.org")
    logger.log(f'crossref cn bibtex .... for {doi}')

    try:
        bibtex_entry_str = cn.content_negotiation(ids=doi, format="bibentry")
        json_entry = cn.content_negotiation(ids=doi, format="citeproc-json")
        return bibtex_entry_str, json_entry, 'ok'
    except Exception as e:
        print(f'cn.content_negotiation exception: {e}')
        return None, None, '!ok'


def doi_to_doi_org_bibtex_entry(doi: str, logger: Logger) -> Tuple[Optional[str], Optional[str], str]:
    """
    Get BibTeX entry from DOI using doi.org content negotiation.
    
    Args:
        doi: DOI string
        logger: Logger instance
        
    Returns:
        Tuple of (bibtex_entry_str, json_entry, status)
    """
    import urllib.request
    logger.log(f'doi.org cn bibtex .... for {doi}')

    try:
        req = urllib.request.Request(
            url=f"https://doi.org/{doi}",
            headers={"Accept": "application/x-bibtex"}
        )
        with urllib.request.urlopen(req) as response:
            bibtex_entry_str = response.read().decode('utf-8')
        
        req = urllib.request.Request(
            url=f"https://doi.org/{doi}",
            headers={"Accept": "application/vnd.citationstyles.csl+json"}
        )
        with urllib.request.urlopen(req) as response:
            json_entry = response.read().decode('utf-8')
        
        return bibtex_entry_str, json_entry, 'ok'
    except Exception as e:
        print(f'doi.org exception: {e}')
        return None, None, '!ok'


def dois_to_bibtex_entries(
    store: Dict[str, EntryStore],
    config: Config,
    logger: Logger
) -> None:
    """
    Fetch BibTeX entries for all DOIs in the store.
    
    Args:
        store: Dictionary of EntryStore instances
        config: Configuration options
        logger: Logger instance
    """
    logger.log('dois_to_bibtex_entries ....')
    store_search: Dict[str, EntryStore] = {}
    
    # Build list of entries to search
    for key, entry_store in store.items():
        if entry_store.crossref_query_status == 'ok':
            if entry_store.doi_to_bibtex_status != 'ok':
                store_search[key] = entry_store
            else:
                logger.log(f'   use cache for {entry_store.input["ID"]}')
        else:
            logger.log(f'crossref query for {entry_store.input["ID"]} has failed')

    if len(store_search) > 0:
        timer = Timer()
        timer.start()
        n_jobs = min(len(store_search), config.number_of_parallel_request)
        
        if doi_to_bibtex_entry_server == 'doi.org':
            results = Parallel(n_jobs=n_jobs)(
                delayed(doi_to_doi_org_bibtex_entry)(entry.found_doi, logger)
                for entry in store_search.values()
            )
        else:
            results = Parallel(n_jobs=n_jobs)(
                delayed(doi_to_crossref_bibtex_entry)(entry.found_doi, logger)
                for entry in store_search.values()
            )
        timer.stop()

        for (key, entry_store), result in zip(store_search.items(), results):
            bibtex_entry_str, json_entry, status = result
            entry_store.doi_to_bibtex_status = status
            
            if status == 'ok':
                entry_store.crossref_json_entry = json_entry
                bp = BibTexParser(interpolate_strings=False)
                bib_database = bp.parse(bibtex_entry_str)
                
                entries_list = list(bib_database.entries)
                if len(entries_list) == 0:
                    entry_store.doi_to_bibtex_status = '!ok'
                    logger.log(f'WARNING: bad format for bibtex from crossref {entry_store.input["ID"]}')
                else:
                    entry_store.crossref_bibtex_entry = entries_list[0]


# =============================================================================
# Unpaywall API functions
# =============================================================================
from unpywall.utils import UnpywallCredentials
from unpywall import Unpywall

# Initialize Unpaywall credentials
UnpywallCredentials('vincent.acary@inria.fr')


def unpywall_query(title: str, is_oa: bool, logger: Logger) -> Tuple[Optional[Any], str, str]:
    """
    Query Unpaywall API by title.
    
    Args:
        title: Publication title
        is_oa: Filter for open access only
        logger: Logger instance
        
    Returns:
        Tuple of (query_result, message, status)
    """
    try:
        query = Unpywall.query(query=title, is_oa=is_oa, errors='ignore')
        if query is not None:
            msg = f'{{Unpywall.query on title returns results with is_oa={is_oa}}}'
            logger.log(msg)
            status = 'query ok'
        else:
            msg = f'{{Unpywall.query on title returns None with is_oa={is_oa}}}'
            logger.log(msg)
            status = 'query none'
    except Exception as e:
        query = None
        msg = f'[warning]: Unpywall.query on title on unpaywall failed !!! {e}'
        logger.log(msg)
        status = 'not found'
    
    return query, msg, status


def unpywall_doi(doi: str, logger: Logger) -> Tuple[Optional[Any], str, str]:
    """
    Query Unpaywall API by DOI.
    
    Args:
        doi: DOI string
        logger: Logger instance
        
    Returns:
        Tuple of (query_result, message, status)
    """
    try:
        query = Unpywall.doi(dois=[doi], errors='ignore')
        if query is not None:
            msg = '{Unpywall.doi returns results}'
            status = 'doi found'
        else:
            logger.log('[error]: doi query on unpaywall is None !!!')
            msg = '{Unpywall.doi returns None}'
            status = 'doi not found'
    except Exception as e:
        logger.log(f'[warning]: Unpywall.doi failed !!! {e}')
        msg = f'{{Unpywall.doi failed}}: {e}'
        status = 'doi failed'
        query = None

    return query, msg, status


def unpaywall_get_oai_url(doi_query: Optional[Any], logger: Logger) -> Tuple[str, str]:
    """
    Extract OAI URL from Unpaywall query result.
    
    Args:
        doi_query: Unpaywall query result DataFrame
        logger: Logger instance
        
    Returns:
        Tuple of (oai_url, status)
    """
    oai_url = 'oai url not found'
    status = 'oai url not found'

    if doi_query is None:
        return oai_url, status

    if doi_query.get('best_oa_location.url_for_pdf') is not None:
        if doi_query['best_oa_location.url_for_pdf'][0] is not None:
            oai_url = urllib.parse.unquote(
                doi_query['best_oa_location.url_for_pdf'][0],
                errors='replace')
            status = 'oai url found'
            logger.log(f'unpaywall oai url: {oai_url}')

    if doi_query.get('best_oa_location.url') is not None:
        if doi_query.get('best_oa_location.url')[0] is not None:
            oai_url = urllib.parse.unquote(
                doi_query.get('best_oa_location.url')[0], errors='replace')
            status = 'oai url found'
            logger.log(f'unpaywall oai url: {oai_url}')

    if doi_query.get('best_oa_location.url_for_landing_page') is not None:
        if doi_query.get('best_oa_location.url_for_landing_page')[0] is not None:
            oai_url = urllib.parse.unquote(
                doi_query.get('best_oa_location.url_for_landing_page')[0],
                errors='replace')
            status = 'oai url found'
            logger.log(f'unpaywall oai url: {oai_url}')

    return oai_url, status


def unpaywall_oais_from_crossref_dois(
    entries: List[Dict[str, Any]],
    store: Dict[str, EntryStore],
    config: Config,
    logger: Logger
) -> None:
    """
    Query Unpaywall for all entries with valid Crossref DOIs.
    
    Args:
        entries: List of BibTeX entries
        store: Dictionary of EntryStore instances
        config: Configuration options
        logger: Logger instance
    """
    if not entries:
        return
    
    timer = Timer()
    timer.start()
    results = Parallel(n_jobs=len(entries))(
        delayed(unpywall_doi)(store[entry.get('ID')].found_doi, logger)
        for entry in entries
    )
    timer.stop()

    for entry, result in zip(entries, results):
        entry_id = entry.get('ID')
        doi_query, unpaywall_msg, unpaywall_status = result
        
        entry_store = store[entry_id]
        entry_store.unpaywall_msg = unpaywall_msg
        entry_store.unpaywall_status = [unpaywall_status]

        if doi_query is not None:
            if config.output_unpaywall_data:
                doi_query_dict = doi_query.to_dict('dict')
                print(doi_query_dict)
                entry_store.unpaywall_data = json.dumps(doi_query_dict, indent=4)

            if unpaywall_status == 'doi found':
                oai_url, status = unpaywall_get_oai_url(doi_query, logger)
                entry_store.oai_url = oai_url
                entry_store.unpaywall_status.append(status)

                # Detect if OAI is from arXiv or HAL
                oai_host_type = None
                oai_repository_institution = None

                if doi_query.get('best_oa_location.host_type') is not None:
                    oai_host_type = doi_query.get('best_oa_location.host_type')[0]
                
                if doi_query.get('best_oa_location.repository_institution') is not None:
                    oai_repository_institution = doi_query.get('best_oa_location.repository_institution')[0]

                if (oai_host_type == 'repository' and oai_repository_institution is not None):
                    if 'arXiv' in oai_repository_institution:
                        print(doi_query)
                        entry_store.oai_url_for_landing_page = \
                            doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print(f'landing: {entry_store.oai_url_for_landing_page}')
                        entry_store.oai_type = 'arXiv'
                    
                    if 'HAL' in oai_repository_institution:
                        entry_store.oai_type = 'HAL'
                        entry_store.oai_url_for_landing_page = \
                            doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print(f'landing: {entry_store.oai_url_for_landing_page}')


# =============================================================================
# Validation and Interactive Mode
# =============================================================================

class InteractiveDecisions:
    """
    Track user decisions during interactive mode.
    
    Replaces the global lists user_forced_entries and user_skipped_entries.
    """
    
    def __init__(self):
        self.forced: List[str] = []
        self.skipped: List[str] = []
    
    def force_entry(self, entry_id: str) -> None:
        """Mark entry as forced valid."""
        self.forced.append(entry_id)
    
    def skip_entry(self, entry_id: str) -> None:
        """Mark entry as skipped."""
        self.skipped.append(entry_id)
    
    def has_decisions(self) -> bool:
        """Check if any decisions were made."""
        return bool(self.forced or self.skipped)
    
    def print_suggestions(self, config: Config, logger: Logger) -> None:
        """Print command-line suggestions based on decisions."""
        if not self.has_decisions():
            return
        
        lines = [
            "",
            "="*70,
            "Based on your interactive choices, use these options for future runs:",
            "="*70,
        ]
        
        if self.forced:
            forced_list = ','.join(self.forced)
            lines.extend([
                "",
                "# Force validation for these entries:",
                f"--forced-valid-crossref-entry={forced_list}",
            ])
        
        if self.skipped:
            skipped_list = ','.join(self.skipped)
            lines.extend([
                "",
                "# Skip double-check for these entries:",
                f"--skip-double-check={skipped_list}",
            ])
        
        # Combined command suggestion
        cmd_parts = [sys.argv[0]]
        if self.forced:
            cmd_parts.append(f"--forced-valid-crossref-entry={','.join(self.forced)}")
        if self.skipped:
            cmd_parts.append(f"--skip-double-check={','.join(self.skipped)}")
        cmd_parts.append(config.filename)
        
        lines.extend([
            "",
            "# Combined command:",
            " ".join(cmd_parts),
            "",
            "="*70,
        ])
        
        for line in lines:
            logger.log(line)


def interactive_menu(
    entry_id: str,
    input_bibtex_entry: Dict[str, Any],
    crossref_bibtex_entry: Dict[str, Any],
    decisions: InteractiveDecisions,
    logger: Logger
) -> Tuple[bool, bool]:
    """
    Show interactive menu for invalid entries.
    
    Args:
        entry_id: ID of the entry
        input_bibtex_entry: Original BibTeX entry
        crossref_bibtex_entry: Crossref BibTeX entry
        decisions: InteractiveDecisions instance to track choices
        logger: Logger instance
        
    Returns:
        Tuple of (flag_skip, flag_forced_valid)
    """
    print("\n" + "="*60)
    print(f"Entry '{entry_id}' validation failed.")
    print("="*60)
    print("Options:")
    print("  [f]orce - Force validation (use Crossref entry)")
    print("  [s]kip  - Skip double check (keep input entry)")
    print("  [c]ontinue - Do nothing and continue")
    print("="*60)
    
    flag_skip = False
    flag_forced_valid = False
    
    while True:
        try:
            choice = input("Your choice [f/s/c]: ").strip().lower()
            if choice in ['f', 'force']:
                flag_forced_valid = True
                decisions.force_entry(entry_id)
                print(f"  -> Entry '{entry_id}' will be forced valid.")
                break
            elif choice in ['s', 'skip']:
                flag_skip = True
                decisions.skip_entry(entry_id)
                print(f"  -> Entry '{entry_id}' will be skipped.")
                break
            elif choice in ['c', 'continue', '']:
                print(f"  -> Continuing without changes.")
                break
            else:
                print("Invalid choice. Please enter 'f', 's', or 'c'.")
        except (EOFError, KeyboardInterrupt):
            print("\n  -> Continuing without changes.")
            break
    
    return flag_skip, flag_forced_valid


def double_check_bibtex_entries(
    input_bibtex_entry: Dict[str, Any],
    crossref_bibtex_entry: Dict[str, Any],
    config: Config,
    decisions: InteractiveDecisions,
    logger: Logger
) -> Tuple[str, str]:
    """
    Validate Crossref entry against input entry.
    
    Args:
        input_bibtex_entry: Original BibTeX entry from input file
        crossref_bibtex_entry: BibTeX entry from Crossref
        config: Configuration options
        decisions: InteractiveDecisions to track user choices
        logger: Logger instance
        
    Returns:
        Tuple of (status, check_details)
            status: 'valid', '!valid', 'skipped', or 'valid'
            check_details: String describing what was checked
    """
    entry_id = input_bibtex_entry.get('ID')
    flag_skip = entry_id in config.skip_double_check
    flag_forced_valid = entry_id in config.forced_valid_crossref_entry

    check = ''
    flag = True

    # Check entry type (useful when same title/year for conference and journal)
    if input_bibtex_entry.get('ENTRYTYPE') != crossref_bibtex_entry.get('ENTRYTYPE'):
        check += 'entry type: !ok '
        flag = False
        logger.log(
            f'[Warning] input_bibtex_entry type are different.',
            input_bibtex_entry.get('ENTRYTYPE'),
            crossref_bibtex_entry.get('ENTRYTYPE')
        )
        print(f'| {entry_id} | type are different |')

    # Check year
    year_1_text = input_bibtex_entry.get('year', '')
    date = input_bibtex_entry.get('date', '')
    if year_1_text == '':
        if date == '':
            logger.log('[Warning] missing year and date in input file')
        else:
            year_1_text = date.split('-')[0]

    year_2_text = crossref_bibtex_entry.get('year', '')

    if year_1_text != year_2_text and year_2_text != '':
        check += 'year: !ok '
        flag = False
        logger.log(
            f'[Warning] years are different.\n year in input bibtex : {year_1_text}\n'
            f' year crossref bibtex : {year_2_text}'
        )
        print(f'\n| {entry_id} | years are different |\n')
    elif year_2_text == '':
        check += 'year: none(2)'
    elif year_1_text == '':
        check += 'year: none(1)'
    else:
        check += 'year: ok '

    # Check title
    document_1_text = input_bibtex_entry.get('title', '').lower().replace('{', '').replace('}', '')
    document_2_text = crossref_bibtex_entry.get('title', '').lower().replace('{', '').replace('}', '')
    document_2_text = document_2_text.replace('\\textquotesingle', "'").replace('\\textendash', '--').replace('\\textemdash', '-')

    document_1_words = document_1_text.split()
    document_2_words = document_2_text.split()
    intersection = set(document_1_words).symmetric_difference(set(document_2_words))

    if len(intersection) < 1:
        check += 'title: ok+ '
    elif len(intersection) < 3:
        check += 'title: ok- '
        logger.log(f'[Warning] small difference in title {intersection}')
        print(f'| {entry_id}\n| small difference in title |\n')
    else:
        check += 'title: !ok '
        flag = False
        if config.stop_on_bad_check and not flag_skip:
            logger.log(f'[Warning] title in input bibtex:\n{document_1_text}\n')
            logger.log(f'[Warning] title in crossref bibtex:\n{document_2_text}\n')
            print(f'difference: {intersection} {len(intersection)}')
            print(f'\n| {entry_id} | title are different |\n')
            
    if not flag and config.stop_on_bad_check:

        
        logger.log('input bibtex entry :')
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(input_bibtex_entry)
        print(writer.write(db))
        
        logger.log('crossref bibtex entry :')
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(crossref_bibtex_entry)
        print(writer.write(db))

        logger.log(
            'hints: you may manually add crossref_doi ={foo} in the input entry '
            'of the bibtex file to fix the issue '
        )
        
        # Interactive menu for handling invalid entries
        if config.stop_on_bad_check and not flag_skip and not flag_forced_valid:
            flag_skip, flag_forced_valid = interactive_menu(
                entry_id, input_bibtex_entry, crossref_bibtex_entry,
                decisions, logger
            )

    if flag:
        status = 'valid'
    else:
        status = '!valid'

    if flag_skip:
        status = 'skipped'

    if flag_forced_valid:
        status = 'valid'
        check += 'forced valid'

    return status, check


# =============================================================================
# BibTeX Entry Processing
# =============================================================================

def add_tag_doi_in_entry(doi: str, entry: Dict[str, Any]) -> str:
    """
    Add DOI tag to a BibTeX entry.
    
    Args:
        doi: DOI string
        entry: BibTeX entry dictionary
        
    Returns:
        Action description
    """
    entry['crossref_doi'] = doi
    tag = f'\\tagDOI{{{entry["crossref_doi"]}}}'

    if entry.get('addendum_item'):
        entry['addendum_item'].append(tag)
    else:
        entry['addendum_item'] = [tag]

    return 'add doi'


def add_tag_oai_url_in_entry(entry_store: EntryStore, entry: Dict[str, Any]) -> str:
    """
    Add OAI URL tag to a BibTeX entry.
    
    Args:
        entry_store: EntryStore instance for the entry
        entry: BibTeX entry dictionary
        
    Returns:
        Action description
    """
    oai_url = entry_store.oai_url
    entry['unpaywalloaiurl'] = oai_url
    latex_tag = None
    final_url = oai_url

    if entry_store.oai_type == 'arXiv':
        latex_tag = '\\tagARXIV{'
        final_url = entry_store.oai_url_for_landing_page
        print(final_url)
    elif entry_store.oai_type == 'HAL':
        fake_landing_page = entry_store.oai_url_for_landing_page
        fake_landing_page_split = fake_landing_page.split('/file/')
        if len(fake_landing_page_split) > 1:
            latex_tag = '\\tagHAL{'
            final_url = fake_landing_page_split[0]
        else:
            latex_tag = '\\tagHAL{'
            final_url = entry_store.oai_url_for_landing_page
        print(final_url)
    else:
        latex_tag = '\\tagOAI{'

    if latex_tag is not None:
        tag = f'{latex_tag}{final_url}}}'
        if entry.get('addendum_item'):
            entry['addendum_item'].append(tag)
        else:
            entry['addendum_item'] = [tag]

    return 'add oai'


def complete_addendum_in_entry(entry: Dict[str, Any]) -> None:
    """Merge addendum_item list into addendum field."""
    if entry.get('addendum'):
        addendum = entry['addendum']
        if entry.get('addendum_item'):
            entry['addendum_item'].append(addendum)
            print(f'addendum[item] {entry.get("addendum_item")}')
    
    if entry.get('addendum_item'):
        entry['addendum'] = ', '.join(entry['addendum_item'])
        entry.pop('addendum_item')


def astyle_author_crossref_bibtex(crossref_author: str) -> str:
    """
    Format author names from Crossref BibTeX style.
    
    Args:
        crossref_author: Author string from Crossref
        
    Returns:
        Formatted author string
    """
    author_list = crossref_author.split(' and ')
    new_author_list = []
    for a in author_list:
        parts = a.split(' ')
        lastname = parts.pop().lower().title()
        firstname = ' '.join(parts).lower().title()
        new_author_list.append(f'{lastname}, {firstname}')
    return ' and '.join(new_author_list)


def astyle_author_crossref_json(json_entry: str) -> str:
    """
    Format author names from Crossref JSON response.
    
    Args:
        json_entry: JSON string from Crossref
        
    Returns:
        Formatted author string
    """
    d = json.loads(json_entry)
    author = d.get('author', [])
    author_bibtex = []
    for a in author:
        family = a.get('family')
        if family:
            if family.isupper():
                family = family.title()
            
            given = a.get('given')
            if given:
                author_bibtex.append(f'{family}, {given}')
            else:
                author_bibtex.append(family)

    return ' and '.join(author_bibtex)


def ad_hoc_build_output_bibtex_entries(
    store: Dict[str, EntryStore],
    config: Config,
    logger: Logger
) -> None:
    """
    Build final output BibTeX entries from all gathered data.
    
    Args:
        store: Dictionary of EntryStore instances
        config: Configuration options
        logger: Logger instance
    """
    logger.log('ad_hoc_build_output_bibtex_entries')



    k = 0
    for key, entry_store in store.items():
        if entry_store.duplicate:
            continue

        input_bibtex_entry = entry_store.input

        if entry_store.doi_to_bibtex_status != 'ok':
            entry_store.output_bibtex_entry = input_bibtex_entry
            continue

        crossref_bibtex_entry = entry_store.crossref_bibtex_entry
        entry_id = input_bibtex_entry.get('ID')
        logger.log(f'## bibtex_entry {k} ID : {entry_id}')

        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(input_bibtex_entry)
        logger.log(f'Original input bibtex entry: \n{writer.write(db)}')
        
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(crossref_bibtex_entry)
        logger.log(f'crossref bibtex entry: \n{writer.write(db)}')

        entry_store.action = ['', '']

        # Start from base entry
        entry_store.output_bibtex_entry = input_bibtex_entry.copy()
        output_bibtex_entry = entry_store.output_bibtex_entry

        if entry_id not in config.skip_double_check:
            if entry_store.found_doi_status == 'valid':
                use_entry = ['journal', 'author', 'publisher', 'volume',
                             'number', 'booktitle', 'pages']

                # Remove keys that user wants to keep from input
                for i in range(len(config.keep_entry)):
                    if config.keep_entry[i] == entry_id:
                        if i + 1 < len(config.keep_entry) and config.keep_entry[i + 1] in use_entry:
                            use_entry.remove(config.keep_entry[i + 1])

                for bkey in use_entry:
                    if crossref_bibtex_entry.get(bkey):
                        if bkey == 'author':
                            output_bibtex_entry[bkey] = astyle_author_crossref_json(
                                entry_store.crossref_json_entry
                            )
                        else:
                            output_bibtex_entry[bkey] = crossref_bibtex_entry[bkey]

                entry_store.action[0] = add_tag_doi_in_entry(
                    entry_store.found_doi, output_bibtex_entry
                )

                if len(entry_store.unpaywall_status) > 1 and entry_store.unpaywall_status[1] == 'oai url found':
                    entry_store.action[1] = add_tag_oai_url_in_entry(
                        entry_store, output_bibtex_entry
                    )

                complete_addendum_in_entry(output_bibtex_entry)

        # Remove unwanted fields
        for field in ['month', 'pdf', 'url', 'doi']:
            if output_bibtex_entry.get(field):
                output_bibtex_entry.pop(field)
        
        if output_bibtex_entry.get('issue') and output_bibtex_entry.get('number'):
            output_bibtex_entry.pop('number')

        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(output_bibtex_entry)
        logger.log(f'output edited bibtex entry: \n{writer.write(db)}')


        k += 1


# =============================================================================
# File I/O Operations
# =============================================================================

class BibtexIO:
    """Handle all BibTeX file I/O operations."""
    
    @staticmethod
    def load(filepath: str, logger: Logger) -> 'BibDatabase':
        """Load BibTeX file and return parsed database."""

        
        with open(filepath) as f:
            bibtex_str = f.read()
        
        # Use interpolate_strings=False to handle undefined strings
        bp = BibTexParser(
            interpolate_strings=False,
            ignore_nonstandard_types=False
        )
        return bp.parse(bibtex_str)
    
    @staticmethod
    def save(database: 'BibDatabase', filepath: str, header: Optional[str] = None) -> None:
        """Save BibTeX database to file."""

        
        writer = BibTexWriter()
        writer.display_order = ['author', 'title', 'journal', 'year']
        
        with open(filepath, 'w', encoding='utf-8') as f:
            bibtex_str = dumps(database, writer)
            if header:
                f.write(header + '\n')
            f.write(bibtex_str)
    
    @staticmethod
    def replace_curious_characters(filepath: str) -> None:
        """Replace problematic characters in the output file."""
        text_to_replace = [
            ('$\\mathsemicolon$', ';'),
            ('{\\&}amp;', '\\&'),
            ('&amp;', '\\&'),
            ('À', '{\\`A}'),
            ('\\i', 'i'),
            ('–', '-'),
        ]

        with open(filepath, "r", encoding='utf-8') as f:
            content = f.read()

        for old, new in text_to_replace:
            if old in content:
                print(f'Match Found. replace {old} by {new}')
                content = content.replace(old, new)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


# =============================================================================
# Main Processing Class
# =============================================================================

class BibtexProcessor:
    """
    Main class for processing BibTeX files.
    
    Encapsulates all processing logic and state, eliminating global variables.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = Logger(config.verbose)
        self.decisions = InteractiveDecisions()
        self.store: Dict[str, EntryStore] = {}
        self.base_filename = os.path.splitext(config.filename)[0] if config.filename else ''
        self.output_file = f'{self.base_filename}_edited.bib'
        self.pickle_name = f'{self.base_filename}_cache.pickle'
    
    def load_cache(self) -> None:
        """Load cached data from pickle file."""
        if os.path.exists(self.pickle_name):
            with open(self.pickle_name, 'rb') as handle:
                old_store = pickle.load(handle)
                # Convert dictionaries back to EntryStore objects
                for key, data in old_store.items():
                    if isinstance(data, dict):
                        self.store[key] = EntryStore.from_dict(data)
                    else:
                        self.store[key] = data
    
    def save_cache(self) -> None:
        """Save current state to pickle file."""
        with open(self.pickle_name, 'wb') as handle:
            # Convert EntryStore objects to dictionaries for serialization
            dict_store = {k: v.to_dict() for k, v in self.store.items()}
            pickle.dump(dict_store, handle, protocol=pickle.HIGHEST_PROTOCOL)
    
    def initialize_store(self, bib_database: 'BibDatabase') -> None:
        """Initialize store from BibTeX database."""
        # Remove entries from cache that are no longer in the input file
        current_entries = {entry.get('ID') for entry in bib_database.entries}
        keys_to_remove = [k for k in self.store if k not in current_entries]
        for k in keys_to_remove:
            self.logger.log(f'entry in cache {k} no longer in input bibtex file')
            del self.store[k]
        
        # Update or create EntryStore for each entry
        for entry in bib_database.entries:
            entry_id = entry.get('ID')
            
            if entry_id in self.store:
                existing = self.store[entry_id]
                if existing.input == entry:
                    self.logger.log(f'    entry {entry_id} has not changed. using cache')
                else:
                    self.logger.log(f'    entry {entry_id} has changed. cache removed')
                    self.store[entry_id] = EntryStore(input=entry)
            else:
                self.store[entry_id] = EntryStore(input=entry)
    
    def remove_duplicates(self) -> int:
        """Remove duplicate entries with the same DOI."""
        dois: List[Tuple[str, str]] = []
        for key, entry_store in self.store.items():
            if entry_store.found_doi_status == 'valid' and entry_store.found_doi:
                dois.append((entry_store.found_doi, key))
        
        seen: Set[str] = set()
        duplicates = []
        
        for doi, key in dois:
            if doi in seen:
                duplicates.append(key)
                self.store[key].duplicate = True
            else:
                seen.add(doi)
        
        return len(duplicates)
    
    def generate_report(self) -> None:
        """Generate summary report."""
        e_idx = 0
        fmt_string = '# {:<6} {:<30} {:<10} {:<10} {:<40} {:<10} {:<10}'
        
        header = ' ' + '-' * 42 + '------------------------------------------------#\n' + ' ' * 18 + ' {:<40}  ------------------------------------------------#'
        self.logger.log(header.format('7. Report'))
        
        self.logger.log(fmt_string.format('number', 'id', 'doi query', 'doi', 'check', 'action', 'unpaywall status'))
        self.logger.log(fmt_string.format('', '', '', '', '', '', 'unpaywall msg'))
        
        for key, entry_store in self.store.items():
            entry_id = entry_store.input.get('ID')
            
            if entry_store.duplicate:
                self.logger.log(fmt_string.format(e_idx, entry_id, 'duplicate', '', '', '', ''))
            else:
                self.logger.log(fmt_string.format(
                    e_idx, entry_id,
                    str(entry_store.crossref_query_status),
                    str(entry_store.found_doi_status),
                    str(entry_store.check),
                    str(entry_store.action[0] if entry_store.action else ' '),
                    str(entry_store.unpaywall_status)
                ))
                self.logger.log(fmt_string.format(
                    '', '', '', '', '',
                    str(entry_store.action[1] if len(entry_store.action) > 1 else ' '),
                    str(entry_store.unpaywall_msg)
                ))
            e_idx += 1
    
    def generate_summary_table(self) -> None:
        """Generate a Markdown summary table of problematic entries."""
        fmt_string_2 = '| {:<40} | {:<20} | {:<60} | {:<8} | {:<8} | {:<10} |'
        
        print("")
        print("|-")
        print(fmt_string_2.format(
            'Id', 'found doi status', 'check', 'forced', 'skip', 'comment'
        ))
        print("|-")
        
        for key, entry_store in self.store.items():
            entry_id = entry_store.input.get('ID')
            
            # Check if entry was forced or skipped (from config or interactive decisions)
            test_forced = (
                entry_id in self.config.forced_valid_crossref_entry or
                entry_id in self.decisions.forced
            )
            test_skipped = (
                entry_id in self.config.skip_double_check or
                entry_id in self.decisions.skipped
            )
            
            # Only show entries that are duplicates, invalid, forced, or skipped
            if entry_store.duplicate:
                print(fmt_string_2.format(
                    str(entry_id), 'duplicate', '', '', '', ''
                ))
            elif entry_store.found_doi_status == '!valid' or test_forced or test_skipped:
                print(fmt_string_2.format(
                    entry_id,
                    str(entry_store.found_doi_status),
                    str(entry_store.check),
                    str(bool(test_forced)),
                    str(test_skipped),
                    ' '
                ))
        
        print("|-")
        print("")
    
    def write_output(self, n_bibtex_entries: int, n_duplicates: int) -> None:
        """Write output BibTeX file."""
        edited_bib_db = BibDatabase()
        for entry_store in self.store.values():
            if not entry_store.duplicate and entry_store.output_bibtex_entry:
                edited_bib_db.entries.append(entry_store.output_bibtex_entry)
        
        n_edited = len(edited_bib_db.entries)
        
        self.logger.log(f'## number of entries (input) {n_bibtex_entries}')
        self.logger.log(f'## number of duplicate entries (input) {n_duplicates}')
        self.logger.log(f'## number of entries (output) {n_edited}')
        
        if n_edited + n_duplicates != n_bibtex_entries:
            self.logger.log(
                f'[WARNING]: The number of output entries is not same as the input: '
                f'{n_edited} != {n_bibtex_entries + n_duplicates}'
            )
        
        header = (
            "@Comment{This file has been generated with the script jtcam_bibtex_editing.py}\n"
            "@Comment{Do not edit it directly by yourself. Modify the source file if needed}"
        )
        
        BibtexIO.save(edited_bib_db, self.output_file, header)
        BibtexIO.replace_curious_characters(self.output_file)
    
    def split_output(self) -> None:
        """Split output into individual BibTeX files."""
        self.logger.log(' ' + '-' * 42 + '------------------------------------------------#\n' + ' ' * 18 + ' {:<40}  ------------------------------------------------#'.format('10. Splitted bib entries'))
        
        dir_name = 'splitted_bibtex_entries'
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
        
        list_bib_file = []
        
        for entry_store in self.store.values():
            if entry_store.duplicate or not entry_store.output_bibtex_entry:
                continue
            
            writer = BibTexWriter()
            edited_bib = BibDatabase()
            edited_bib.entries.append(entry_store.output_bibtex_entry)
            
            output_path = os.path.join(dir_name, entry_store.output_bibtex_entry['ID'] + '.bib')
            
            with open(output_path, 'w') as f:
                f.write(dumps(edited_bib, writer))
            
            BibtexIO.replace_curious_characters(output_path)
            
            str_file = r"\ "[0] + f'addbibresource{{{output_path}}}'
            list_bib_file.append(str_file)
        
        with open('splitted_bib_entries.tex', 'w') as f:
            for line in list_bib_file:
                f.write(f"{line}\n")
        
        self.logger.log('splitted bib entries are in the folder: splitted_bibtex_entries')
        self.logger.log('\\input(splitted_bib_entries.tex) to use it')
    
    def run(self) -> None:
        """Run the complete processing pipeline."""
        if not self.config.filename or not os.path.exists(self.config.filename):
            self.logger.log(f'bib file {self.config.filename} does not exist')
            return
        
        # Load bib file
        header = ' ' + '-' * 42 + '------------------------------------------------#\n' + ' ' * 18 + ' {:<40}  ------------------------------------------------#'
        self.logger.log(header.format('1. Parse input bibtex file'))
        
        bib_database = BibtexIO.load(self.config.filename, self.logger)
        n_bibtex_entries = len(bib_database.entries)
        self.logger.log(f'# number of entries (input) {n_bibtex_entries}')
        
        # Limit entries if needed
        if n_bibtex_entries > self.config.max_entry:
            bib_database.entries = bib_database.entries[:self.config.max_entry]
        
        # Load cache and initialize store
        self.load_cache()
        self.initialize_store(bib_database)
        
        # Step 2: Crossref DOI search
        self.logger.log(header.format('2. Crossref doi search'))
        bibtex_entries_to_crossref_dois(self.store, self.config, self.logger)
        self.save_cache()
        
        # Step 3: Get BibTeX entries from Crossref
        self.logger.log(header.format('3. get bibtex from crossref'))
        dois_to_bibtex_entries(self.store, self.config, self.logger)
        self.save_cache()
        
        # Step 4: Validate entries
        self.logger.log(header.format('4. validation of crossref_bibtex_entry'))
        
        valid_crossref_bib_db = BibDatabase()
        
        k = 0
        for key, entry_store in self.store.items():
            entry = entry_store.input
            entry_id = entry.get('ID')
            self.logger.log(f'## entry {k}: {entry_id}')
            
            if entry_store.doi_to_bibtex_status == 'ok':
                entry_store.crossref_bibtex_entry_key = entry_store.crossref_bibtex_entry.get('ID')
                entry_store.crossref_bibtex_entry['ID'] = entry_id
                
                status, check = double_check_bibtex_entries(
                    entry, entry_store.crossref_bibtex_entry,
                    self.config, self.decisions, self.logger
                )
                
                self.logger.log(f'{status} {check}')
                entry_store.check = check
                entry_store.found_doi_status = status
                
                if status == 'valid':
                    valid_crossref_bib_db.entries.append(entry_store.crossref_bibtex_entry)
            else:
                entry_store.found_doi_status = 'failed'
            
            self.logger.log(f'validation results : {entry_store.found_doi_status}\n')
            k += 1
        
        # Remove duplicates
        n_duplicate = self.remove_duplicates()
        
        # Step 5: Query Unpaywall
        self.logger.log(header.format('5. unpaywall oai from doi'))
        unpaywall_oais_from_crossref_dois(valid_crossref_bib_db.entries, self.store, self.config, self.logger)
        self.save_cache()
        
        # Step 6: Build output entries
        self.logger.log(header.format('6. build output bibtex entry'))
        ad_hoc_build_output_bibtex_entries(self.store, self.config, self.logger)
        
        # Step 7: Generate report
        self.generate_report()
        
        # Step 7b: Generate summary table of problematic entries
        self.logger.log(' ' + '-' * 42 + '------------------------------------------------#\n' + ' ' * 18 + ' {:<40}  ------------------------------------------------#'.format('7b. Summary of problematic entries'))
        self.generate_summary_table()
        
        # Step 8: Write output
        self.logger.log(header.format('8. Write output bibtex file'))
        self.write_output(n_bibtex_entries, n_duplicate)
        
        # Step 9: Clean up (done in write_output)
        self.logger.log(header.format('9. Replacements of Latex or html symbols'))
        
        # Step 10: Split output if requested
        if self.config.split_output:
            self.split_output()
        
        # Step 11: Print suggestions
        if self.decisions.has_decisions():
            self.logger.log(header.format('11. Suggested command-line options'))
            self.decisions.print_suggestions(self.config, self.logger)


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point."""
    config = Config.from_command_line(sys.argv)
    processor = BibtexProcessor(config)
    processor.run()


if __name__ == '__main__':
    main()
