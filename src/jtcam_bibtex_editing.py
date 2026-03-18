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

import getopt
import sys
import os
import pprint
import time


class TimerError(Exception):
    """Custom exception for Timer class errors."""
    pass


class Timer:
    """Simple timer class for measuring execution time."""
    
    def __init__(self):
        self._start_time = None

    def start(self):
        """Start the timer."""
        if self._start_time is not None:
            raise TimerError("Timer is running. Use .stop() to stop it")
        self._start_time = time.perf_counter()

    def stop(self):
        """Stop the timer and print elapsed time."""
        if self._start_time is None:
            raise TimerError("Timer is not running. Use .start() to start it")
        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")


class Options:
    """Command-line options handler."""
    
    def __init__(self):
        self.filename = None
        self.verbose = 0
        self.number_of_parallel_request = 2
        self.output_unpaywall_data = False
        self.skip_double_check = []
        self.forced_valid_crossref_entry = []
        self.stop_on_bad_check = False
        self.max_entry = 100000
        self.crossref_search_key = ['author', 'year', 'title']
        self.use_input_doi = True
        self.keep_entry = []
        self.split_output = False

    def usage(self, long=False):
        """Print usage information."""
        print('Usage: {0} [OPTION]... <bib file>'.format(
            os.path.split(sys.argv[0])[1]))
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

    def parse(self):
        """Parse command line arguments."""
        try:
            opts, args = getopt.gnu_getopt(
                sys.argv[1:], '',
                ['help', 'verbose=', 'is-oa',
                 'output-unpaywall-data', 'skip-double-check=',
                 'forced-valid-crossref-entry=',
                 'stop-on-bad-check', 'max-entry=', 'keep-entry=',
                 'split-output'])
            self.configure(opts, args)
        except getopt.GetoptError as err:
            sys.stderr.write('{0}\n'.format(str(err)))
            self.usage()
            exit(2)

    def configure(self, opts, args):
        """Configure options from parsed arguments."""
        for o, a in opts:
            if o == '--help':
                self.usage(long=True)
                exit(0)
            elif o == '--verbose':
                self.verbose = int(a)
            elif o == '--output-unpaywall-data':
                self.output_unpaywall_data = True
            elif o == '--skip-double-check':
                self.skip_double_check = a.split(',')
            elif o == '--forced-valid-crossref-entry':
                self.forced_valid_crossref_entry = a.split(',')
            elif o == '--stop-on-bad-check':
                self.stop_on_bad_check = True
            elif o == '--max-entry':
                self.max_entry = int(a)
            elif o == '--keep-entry':
                self.keep_entry = a.split(',')
            elif o == '--split-output':
                self.split_output = True
        if len(args) > 0:
            self.filename = args[0]
        else:
            self.usage()
            exit(1)


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


def crossref_query(bibliographic):
    """
    Query Crossref API for a bibliographic entry.
    
    Args:
        bibliographic: Search query string (author, title, year, etc.)
        
    Returns:
        dict: Crossref API response
    """
    print_verbose_level(
        'crossref query search starts on {:40.40}...'.format(bibliographic))
    cr = Crossref(
        base_url="https://api.crossref.org",
        mailto="jtcam@episciences.org"
    )

    try:
        x = cr.works(query_bibliographic=bibliographic, limit=1)
    except Exception as e:
        x = {}
        x['status'] = 'bad'
        print_verbose_level('exception is :', e)

    print_verbose_level(
        'crossref query search ends on {:40.40} with status'.format(
            bibliographic), x['status'])
    return x


def crossref_get_doi_from_query_results(x):
    """
    Extract DOI from Crossref query results.
    
    Args:
        x: Crossref API response
        
    Returns:
        str: DOI string or None if not found
    """
    try:
        doi = x['message']['items'][0]['DOI']
    except Exception as e:
        print('result from crossref has no DOI!!', e)
        doi = None
    return doi


def bibtex_entries_to_crossref_dois(store):
    """
    Search for DOIs for all BibTeX entries using Crossref.
    
    Args:
        store: Dictionary containing entry data
    """
    print_verbose_level('Crossref doi search from bibtex input entry')
    bibliographic = {}
    for key in store:
        entry = store[key]['input']
        entry_id = entry.get('ID')
        if opts.use_input_doi and entry.get('doi'):
            # Use existing doi from input, skip search
            print_verbose_level('    use user input doi for ', entry_id)
            store[key]['crossref_query_status'] = 'ok'
            store[key]['found_doi'] = entry.get('doi')
            continue
        else:
            if store[key].get('crossref_query_status', '') != 'ok':
                bibliographic[entry_id] = [entry]
                query_text = []
                for key in opts.crossref_search_key:
                    query_text.append(entry.get(key, ''))
                query_text = ' '.join(query_text)
                bibliographic[entry_id].append(query_text)
            else:
                print_verbose_level('    use cache entry for ', entry_id)
    
    t = Timer()
    t.start()
    if len(bibliographic) > 0:
        n_jobs = min(len(bibliographic), opts.number_of_parallel_request)
        results = Parallel(n_jobs=n_jobs)(
            delayed(crossref_query)(bibliographic[entry_id][1])
            for entry_id in bibliographic)
    t.stop()

    for cnt, entry_id in enumerate(bibliographic):
        entry = bibliographic[entry_id][0]
        entry_id = entry.get('ID')
        if results[cnt]['status'] == 'ok':
            doi = crossref_get_doi_from_query_results(results[cnt])
            if doi is not None:
                store[entry_id]['found_doi'] = doi
                store[entry_id]['crossref_query_status'] = results[cnt]['status']
            else:
                store[entry_id]['crossref_query_status'] = 'bad'


import json

doi_to_bibtex_entry_server = 'crossref'
doi_to_bibtex_entry_server = 'doi.org'


def doi_to_crossref_bibtex_entry(doi):
    """
    Get BibTeX entry from DOI using Crossref content negotiation.
    
    Args:
        doi: DOI string
        
    Returns:
        tuple: (bibtex_entry_str, json_entry, status)
    """
    cr = Crossref(mailto="jtcam@episciences.org")
    print_verbose_level('crossref cn bibtex  .... for ', doi)

    try:
        bibtex_entry_str = cn.content_negotiation(ids=doi, format="bibentry")
        json_entry = cn.content_negotiation(ids=doi, format="citeproc-json")
    except Exception as e:
        print('cn.content_negotiation exception', e)
        return None, None, '!ok'

    return bibtex_entry_str, json_entry, 'ok'


def doi_to_doi_org_bibtex_entry(doi):
    """
    Get BibTeX entry from DOI using doi.org content negotiation.
    
    Args:
        doi: DOI string
        
    Returns:
        tuple: (bibtex_entry_str, json_entry, status)
    """
    import urllib.request
    print_verbose_level('doi.org cn bibtex  .... for ', doi)

    try:
        req = urllib.request.Request(
            url="https://doi.org/" + doi,
            headers={"Accept": "application/x-bibtex"}
        )
        with urllib.request.urlopen(req) as response:
            bibtex_entry_str = response.read().decode('utf-8')
        req = urllib.request.Request(
            url="https://doi.org/" + doi,
            headers={"Accept": "application/vnd.citationstyles.csl+json"}
        )
        with urllib.request.urlopen(req) as response:
            json_entry = response.read().decode('utf-8')
    except Exception as e:
        print('doi.org exception', e)
        return None, None, '!ok'

    return bibtex_entry_str, json_entry, 'ok'


def dois_to_bibtex_entries(store):
    """
    Fetch BibTeX entries for all DOIs in the store.
    
    Args:
        store: Dictionary containing entry data with found_doi
    """
    print_verbose_level('dois_to_bibtex_entries  ....')
    store_search = {}
    # Build list of entries to search
    for key in store:
        if store[key].get('crossref_query_status', '') == 'ok':
            if store[key].get('doi_to_bibtex_status', '') != 'ok':
                store_search[key] = store[key]
            else:
                print_verbose_level('   use cache for ',
                                    store[key]['input']['ID'])
        else:
            print_verbose_level('crossref query for ',
                                store[key]['input']['ID'], ' has failed')

    t = Timer()
    t.start()
    if len(store_search) > 0:
        n_jobs = min(len(store_search), opts.number_of_parallel_request)
        if doi_to_bibtex_entry_server == 'doi.org':
            results = Parallel(n_jobs=n_jobs)(
                delayed(doi_to_doi_org_bibtex_entry)(store[key]['found_doi'])
                for key in store_search)
        else:
            results = Parallel(n_jobs=n_jobs)(
                delayed(doi_to_crossref_bibtex_entry)(store[key]['found_doi'])
                for key in store_search)
    t.stop()

    for cnt, key in enumerate(store_search):
        bibtex_entry_str, json_entry, status = results[cnt]
        store[key]['doi_to_bibtex_status'] = status
        if status == 'ok':
            store[key]['crossref_json_entry'] = json_entry
            bp = BibTexParser(interpolate_strings=False)
            bib_database = bp.parse(bibtex_entry_str)
            entry_nb = 0
            for e in bib_database.entries:
                entry_nb = entry_nb + 1
            if entry_nb == 0:
                store[key]['doi_to_bibtex_status'] = '!ok'
                print_verbose_level(
                    'WARNING:    bad format for bibtex from crossref',
                    store[key]['input']['ID'])
            else:
                for e in bib_database.entries:
                    store[key]['crossref_bibtex_entry'] = e
                    break


# =============================================================================
# Unpaywall API functions
# =============================================================================
# https://pypi.org/project/unpywall/

from unpywall.utils import UnpywallCredentials
UnpywallCredentials('vincent.acary@inria.fr')
from unpywall import Unpywall


def unpywall_query(title, is_oa):
    """
    Query Unpaywall API by title.
    
    Args:
        title: Publication title
        is_oa: Filter for open access only
        
    Returns:
        tuple: (query_result, message, status)
    """
    try:
        query = Unpywall.query(query=title, is_oa=is_oa, errors='ignore')
        if query is not None:
            msg = '{Unpywall.query on title returns results with is_oa=' + str(
                is_oa) + '}'
            print_verbose_level(msg)
            status = 'query ok'
        else:
            msg = '{Unpywall.query on title  returns None with is_oa=' + str(
                is_oa) + '}'
            print_verbose_level(msg)
            status = 'query none'
    except Exception as e:
        query = None
        msg = f'[warning]: Unpywall.query on title on unpaywall failed !!! {e}'
        print_verbose_level(msg)
        status = 'not found'
    return query, msg, status


def unpywall_doi(doi):
    """
    Query Unpaywall API by DOI.
    
    Args:
        doi: DOI string
        
    Returns:
        tuple: (query_result, message, status)
    """
    try:
        query = Unpywall.doi(dois=[doi], errors='ignore')
        if query is not None:
            msg = '{Unpywall.doi returns results}'
            status = 'doi found'
        else:
            print_verbose_level(
                '[error]: doi query on unpaywall is None !!!')
            msg = '{Unpywall.doi returns None}'
            status = 'doi not found'
    except Exception as e:
        print_verbose_level('[warning]: Unpywall.doi  failed !!!', e)
        msg = f'{{Unpywall.doi failed}}: {e}'
        status = 'doi failed'
        query = None

    return query, msg, status


def unpaywall_get_oai_url(doi_query):
    """
    Extract OAI URL from Unpaywall query result.
    
    Args:
        doi_query: Unpaywall query result DataFrame
        
    Returns:
        tuple: (oai_url, status)
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
            print_verbose_level('unpaywall oai url:', oai_url)

    if doi_query.get('best_oa_location.url') is not None:
        if doi_query.get('best_oa_location.url')[0] is not None:
            oai_url = urllib.parse.unquote(
                doi_query.get('best_oa_location.url')[0], errors='replace')
            status = 'oai url found'
            print_verbose_level('unpaywall oai url:', oai_url)

    if doi_query.get('best_oa_location.url_for_landing_page') is not None:
        if doi_query.get('best_oa_location.url_for_landing_page')[0] is not None:
            oai_url = urllib.parse.unquote(
                doi_query.get('best_oa_location.url_for_landing_page')[0],
                errors='replace')
            status = 'oai url found'
            print_verbose_level('unpaywall oai url:', oai_url)

    return oai_url, status


def unpaywall_oais_from_crossref_dois(entries, store):
    """
    Query Unpaywall for all entries with valid Crossref DOIs.
    
    Args:
        entries: List of BibTeX entries
        store: Dictionary containing entry data
    """
    t = Timer()
    t.start()
    results = Parallel(n_jobs=len(entries))(
        delayed(unpywall_doi)(store[entry.get('ID')]['found_doi'])
        for entry in entries)
    t.stop()

    cnt = 0
    for entry in entries:
        doi_query, unpaywall_msg, unpaywall_status = results[cnt]

        store[entry.get('ID')]['unpaywall_msg'] = unpaywall_msg
        store[entry.get('ID')]['unpaywall_status'] = [unpaywall_status]

        if doi_query is not None:
            if opts.output_unpaywall_data:
                doi_query_dict = doi_query.to_dict('dict')
                print(doi_query_dict)
                store[entry.get('ID')]['unpaywall_data'] = json.dumps(
                    doi_query_dict, indent=4)

            if unpaywall_status == 'doi found':
                oai_url, status = unpaywall_get_oai_url(doi_query)
                store[entry.get('ID')]['oai_url'] = oai_url
                store[entry.get('ID')]['unpaywall_status'].append(status)

                # Detect if OAI is from arXiv or HAL
                oai_host_type = None
                oai_repository_institution = None

                if doi_query.get('best_oa_location.host_type') is not None:
                    oai_host_type = doi_query.get(
                        'best_oa_location.host_type')[0]
                if doi_query.get(
                        'best_oa_location.repository_institution') is not None:
                    oai_repository_institution = doi_query.get(
                        'best_oa_location.repository_institution')[0]

                if (oai_host_type == 'repository' and
                        oai_repository_institution is not None):
                    if 'arXiv' in oai_repository_institution:
                        print(doi_query)
                        store[entry.get('ID')]['oai_url_for_landing_page'] = \
                            doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print('landing: ',
                              store[entry.get('ID')]['oai_url_for_landing_page'])
                        store[entry.get('ID')]['oai_type'] = 'arXiv'
                    if 'HAL' in oai_repository_institution:
                        store[entry.get('ID')]['oai_type'] = 'HAL'
                        store[entry.get('ID')]['oai_url_for_landing_page'] = \
                            doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print('landing: ',
                              store[entry.get('ID')]['oai_url_for_landing_page'])

        cnt = cnt + 1


# Global lists to store user decisions during interactive mode
user_forced_entries = []
user_skipped_entries = []


def double_check_bibtex_entries(input_bibtex_entry, crossref_bibtex_entry):
    """
    Validate Crossref entry against input entry.
    
    Compares entry type, year, and title to ensure the Crossref result
    matches the original input.
    
    Args:
        input_bibtex_entry: Original BibTeX entry from input file
        crossref_bibtex_entry: BibTeX entry from Crossref
        
    Returns:
        tuple: (status, check_details)
            status: 'valid', '!valid', 'skipped', or 'valid forced'
            check_details: String describing what was checked
    """
    entry_id = input_bibtex_entry.get('ID')
    flag_skip = entry_id in opts.skip_double_check
    flag_forced_valid = entry_id in opts.forced_valid_crossref_entry

    check = ''
    flag = True

    # Check entry type (useful when same title/year for conference and journal)
    if input_bibtex_entry.get('ENTRYTYPE') != crossref_bibtex_entry.get(
            'ENTRYTYPE'):
        check += 'entry type: !ok '
        flag = flag and False
        print_verbose_level(
            '[Warning] input_bibtex_entry type are different.',
            input_bibtex_entry.get('ENTRYTYPE'),
            crossref_bibtex_entry.get('ENTRYTYPE'))
        print('| ', entry_id, ' | type are different | ' )

    # Check year
    year_1_text = input_bibtex_entry.get('year', '')
    date = input_bibtex_entry.get('date', '')
    if year_1_text == '':
        if date == '':
            print_verbose_level('[Warning] missing year and date in input file')
        else:
            year_1_text = date.split('-')[0]

    year_2_text = crossref_bibtex_entry.get('year', '')

    if year_1_text != year_2_text and year_2_text != '':
        check += 'year: !ok '
        flag = flag and False
        print_verbose_level(
            '[Warning] years are different.\n year in input bibtex :',
            year_1_text, '\n year crossref bibtex :', year_2_text)
        print('\n| ', entry_id, ' | years are different |\n ' )
    elif year_2_text == '':
        check += 'year: none(2)'
    elif year_1_text == '':
        check += 'year: none(1)'
    else:
        check += 'year: ok '

    # Check title
    document_1_text = input_bibtex_entry.get('title', '').lower().replace(
        '{', '').replace('}', '')
    document_2_text = crossref_bibtex_entry.get('title', '').lower().replace(
        '{', '').replace('}', '')
    document_2_text = document_2_text.replace('\\textquotesingle', "'").replace(
        '\\textendash', '--').replace('\\textemdash', '-')

    document_1_words = document_1_text.split()
    document_2_words = document_2_text.split()
    common = set(document_1_words).intersection(set(document_2_words))
    intersection = set(document_1_words).symmetric_difference(
        set(document_2_words))

    if len(intersection) < 1:
        check += 'title: ok+ '
        flag = flag and True
    elif len(intersection) < 3:
        check += 'title: ok- '
        flag = flag and True
        print_verbose_level('[Warning] small difference in title', intersection)
        print('| ', entry_id, '\n| small difference in title  |\n' )
    else:
        check += 'title: !ok '
        flag = flag and False
        if opts.stop_on_bad_check and not flag_skip:
            print_verbose_level('[Warning] title in input bibtex:\n',
                                document_1_text, '\n')
            print_verbose_level('[Warning] title in crossref bibtex:\n',
                                document_2_text, '\n')
            print('difference: ', intersection, len(intersection))
            print('\n| ', entry_id, ' | title are different |\n' )
            
    if not flag and opts.stop_on_bad_check:
        print_verbose_level('input bibtex entry :')
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(input_bibtex_entry)
        print(writer.write(db))
        print_verbose_level('crossref bibtex entry :')
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(crossref_bibtex_entry)
        print(writer.write(db))

        print_verbose_level(
            'hints: you may manually add crossref_doi ={foo} in the input entry '
            'of the bibtex file to fix the issue ')
        
        # Interactive menu for handling invalid entries
        if opts.stop_on_bad_check and not flag_skip and not flag_forced_valid:
            print("\n" + "="*60)
            print(f"Entry '{entry_id}' validation failed.")
            print("="*60)
            print("Options:")
            print("  [f]orce - Force validation (use Crossref entry)")
            print("  [s]kip  - Skip double check (keep input entry)")
            print("  [c]ontinue - Do nothing and continue")
            print("="*60)
            
            while True:
                try:
                    choice = input("Your choice [f/s/c]: ").strip().lower()
                    if choice in ['f', 'force']:
                        flag_forced_valid = True
                        user_forced_entries.append(entry_id)
                        print(f"  -> Entry '{entry_id}' will be forced valid.")
                        break
                    elif choice in ['s', 'skip']:
                        flag_skip = True
                        user_skipped_entries.append(entry_id)
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


import json
import urllib  # For URL encoding compliant with LaTeX


def add_tag_doi_in_entry(doi, entry):
    """
    Add DOI tag to a BibTeX entry.
    
    Args:
        doi: DOI string
        entry: BibTeX entry dictionary
        
    Returns:
        str: Action description
    """
    entry['crossref_doi'] = doi

    if entry.get('addendum_item'):
        entry['addendum_item'].append('\\tagDOI{' + entry['crossref_doi'] + '}')
    else:
        entry['addendum_item'] = ['\\tagDOI{' + entry['crossref_doi'] + '}']

    return 'add doi'


def add_tag_oai_url_in_entry(store_key, entry):
    """
    Add OAI URL tag to a BibTeX entry.
    
    Args:
        store_key: Store dictionary for the entry
        entry: BibTeX entry dictionary
        
    Returns:
        str: Action description
    """
    oai_url = store_key['oai_url']
    entry['unpaywalloaiurl'] = oai_url
    latex_tag = None

    if store_key.get('oai_type') == 'arXiv':
        latex_tag = '\\tagARXIV{'
        oai_url = store_key['oai_url_for_landing_page']
        print(oai_url)
    elif store_key.get('oai_type') == 'HAL':
        fake_landing_page = store_key['oai_url_for_landing_page']
        fake_landing_page_split = fake_landing_page.split('/file/')
        if len(fake_landing_page_split) > 1:
            latex_tag = '\\tagHAL{'
            oai_url = fake_landing_page_split[0]
        else:
            latex_tag = '\\tagHAL{'
            oai_url = store_key['oai_url_for_landing_page']
        print(oai_url)
    else:
        latex_tag = '\\tagOAI{'

    if latex_tag is not None:
        if entry.get('addendum_item'):
            entry['addendum_item'].append(latex_tag + oai_url + '}')
        else:
            entry['addendum_item'] = [latex_tag + oai_url + '}']

    return 'add oai'


def complete_addendum_in_entry(entry):
    """Merge addendum_item list into addendum field."""
    if entry.get('addendum'):
        addendum = entry['addendum']
        if entry.get('addendum_item'):
            entry['addendum_item'].append(addendum)
            print('addendum[item]', entry.get('addendum_item'))
    if entry.get('addendum_item'):
        entry['addendum'] = ', '.join(entry['addendum_item'])
        entry.pop('addendum_item')


def astyle_author_crossref_bibtex(crossref_author):
    """
    Format author names from Crossref BibTeX style.
    
    Args:
        crossref_author: Author string from Crossref
        
    Returns:
        str: Formatted author string
    """
    author_list = crossref_author.split(' and ')
    new_author_list = []
    for a in author_list:
        ll = a.split(' ')
        lastname = ll.pop().lower()
        firstname = ' '.join(ll).lower()
        new_author_list.append(lastname.title() + ', ' + firstname.title())
    author_bibtex = ' and '.join(new_author_list)
    return author_bibtex


def astyle_author_crossref_json(json_entry):
    """
    Format author names from Crossref JSON response.
    
    Args:
        json_entry: JSON string from Crossref
        
    Returns:
        str: Formatted author string
    """
    if doi_to_bibtex_entry_server == 'doi.org' :
        d = json.loads(json_entry)
    else:
        d = json.loads(json_entry)


    
    
    
    author = d['author']
    author_bibtex = []
    for a in author:
        if a.get('family', None):
            family = a['family']
            if family.isupper():
                family = family.title()

            if a.get('given', None):
                given = a['given']
                author_bibtex.append(family + ', ' + given)
            else:
                author_bibtex.append(family)

    author_bibtex = ' and '.join(author_bibtex)
    return author_bibtex


def ad_hoc_build_output_bibtex_entries(store):
    """
    Build final output BibTeX entries from all gathered data.
    
    Args:
        store: Dictionary containing all entry data
    """
    print_verbose_level('ad_hoc_build_output_bibtex_entries')

    k = 0
    for key in store:
        if store[key].get('duplicate', False):
            continue

        input_bibtex_entry = store[key]['input']

        if store[key].get('doi_to_bibtex_status', '') != 'ok':
            store[key]['output_bibtex_entry'] = input_bibtex_entry
            continue

        crossref_bibtex_entry = store[key]['crossref_bibtex_entry']
        print_verbose_level('## bibtex_entry ', k, ' ID : ',
                            input_bibtex_entry.get('ID'))

        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(input_bibtex_entry)
        #print_verbose_level('Original input bibtex entry: \n', writer.write(db))
        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(crossref_bibtex_entry)
        #print_verbose_level('crossref bibtex entry: \n', writer.write(db))

        store[key]['action'] = ['', '']

        # Start from base entry
        store[key]['output_bibtex_entry'] = input_bibtex_entry
        output_bibtex_entry = store[key]['output_bibtex_entry']

        if not (input_bibtex_entry['ID'] in opts.skip_double_check):
            if store[key]['found_doi_status'] == 'valid':
                use_entry = ['journal', 'author', 'publisher', 'volume',
                             'number', 'booktitle', 'pages']

                for i in range(len(opts.keep_entry)):
                    if opts.keep_entry[i] == input_bibtex_entry['ID']:
                        if opts.keep_entry[i + 1] in use_entry:
                            use_entry.remove(opts.keep_entry[i + 1])

                for bkey in use_entry:
                    if crossref_bibtex_entry.get(bkey):
                        if bkey == 'author':
                            output_bibtex_entry[bkey] = \
                                astyle_author_crossref_bibtex(
                                    crossref_bibtex_entry.get(bkey))
                            output_bibtex_entry[bkey] = \
                                astyle_author_crossref_json(
                                    store[key]['crossref_json_entry'])
                        else:
                            output_bibtex_entry[bkey] = \
                                crossref_bibtex_entry[bkey]

                store[key]['action'][0] = add_tag_doi_in_entry(
                    store[key]['found_doi'], output_bibtex_entry)

                if store[key]['unpaywall_status'][1] == 'oai url found':
                    store[key]['action'][1] = add_tag_oai_url_in_entry(
                        store[key], output_bibtex_entry)

                complete_addendum_in_entry(output_bibtex_entry)

        # Remove unwanted fields
        if output_bibtex_entry.get('month'):
            output_bibtex_entry.pop('month')
        if output_bibtex_entry.get('pdf'):
            output_bibtex_entry.pop('pdf')
        if output_bibtex_entry.get('url'):
            output_bibtex_entry.pop('url')
        if output_bibtex_entry.get('doi'):
            output_bibtex_entry.pop('doi')
        if output_bibtex_entry.get('issue'):
            if output_bibtex_entry.get('number'):
                output_bibtex_entry.pop('number')

        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(output_bibtex_entry)
        # print_verbose_level('output edited bibtex entry: \n', writer.write(db))
        # print('------')

        k = k + 1


# =============================================================================
# Main script
# =============================================================================

opts = Options()
opts.parse()

verbose_level = 1


def print_verbose_level(*args, **kwargs):
    """Print message if verbose mode is enabled."""
    if verbose_level:
        print('[jtcam_bibtex_editing]', *args, **kwargs)


base_filename = os.path.splitext(opts.filename)[0]
if os.path.exists(opts.filename):
    output_file = base_filename + '_edited.bib'
else:
    print_verbose_level('bib file', opts.filename, 'is not existing')
    exit(0)

# Header format for verbose output sections
format_verbose_header = (
    ' ' + '-' * 42 +
    '------------------------------------------------#\n' + ' ' * 18 +
    ' {:<40}  ------------------------------------------------#')

# =============================================================================
# 1. Parse input BibTeX file
# =============================================================================
print_verbose_level(format_verbose_header.format('1. Parse input bibtex file'))

from bibtexparser import load, dumps
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase, as_text

with open(opts.filename) as bibtex_file:
    bibtex_str = bibtex_file.read()
    # Use interpolate_strings=False to handle undefined strings
    bp = BibTexParser(interpolate_strings=False,
                      ignore_nonstandard_types=False)
    bib_database = bp.parse(bibtex_str)

n_bibtex_entries = len(bib_database.entries)
print_verbose_level('# number of  entries (input) ', n_bibtex_entries)

bib_database.entries = bib_database.entries[:opts.max_entry]

# =============================================================================
# Initialize data store
# =============================================================================
# The store dictionary collects:
# - input entry: original BibTeX entry from input file
# - output entry: final processed BibTeX entry
# - crossref entry: entry retrieved from Crossref
# - extra info: query status, DOI, OAI URL, etc.

import pickle

pickle_name = base_filename + '_cache.pickle'

if os.path.exists(pickle_name):
    with open(pickle_name, 'rb') as handle:
        store = pickle.load(handle)
else:
    store = {}

# Remove entries from cache that are no longer in the input file
current_entries = [entry.get('ID') for entry in bib_database.entries]
entry_to_pop = []
for entry in store:
    print(entry)
    if entry not in current_entries:
        print('entry in cache ', entry, ' no longer in input bibtex file')
        entry_to_pop.append(entry)
for e in entry_to_pop:
    store.pop(e)

for entry in bib_database.entries:
    entry_id = entry.get('ID')
    dict_entry = store.get(entry_id, {})
    if dict_entry == {}:
        store[entry_id] = {}
        store[entry_id]['input'] = entry
    else:
        # Compare cached entry with current entry
        if dict_entry['input'] == entry:
            print_verbose_level('    entry', entry_id,
                                ' has not changed. we use cache information')
        else:
            store[entry_id] = {}
            store[entry_id]['input'] = entry
            print_verbose_level('    entry', entry_id,
                                ' has changed. cache is removed')

# =============================================================================
# 2. Crossref DOI search
# =============================================================================
# Search for DOIs using the Crossref API with habanero.
# The most relevant DOI is stored in 'found_doi'.
# - Query is built from ['author', 'title', 'year'] of the BibTeX entry
# - The input 'doi' key is not used (to avoid keeping it in output)
# - If 'crossref_doi' is set in input, it is stored as 'found_doi' and search is skipped
print_verbose_level(format_verbose_header.format('2. Crossref doi seach'))

bibtex_entries_to_crossref_dois(store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)

# =============================================================================
# 3. Get BibTeX entries from Crossref using DOIs
# =============================================================================
print_verbose_level(format_verbose_header.format('3. get bibtex from crossef '))

dois_to_bibtex_entries(store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)

# =============================================================================
# 4. Validate Crossref entries
# =============================================================================
# Validation checks year, title, author, and entry type.
# For valid entries, remove duplicates (entries with the same valid DOIs).
print_verbose_level(
    format_verbose_header.format('4. validation of crossref_bibtex_entry '))

k = 0
valid_crossref_bib_db = BibDatabase()
for key in store:
    entry = store[key]['input']
    check = '--'
    print_verbose_level('## entry ', k, ': ', entry.get('ID'))

    if store[key].get('doi_to_bibtex_status', '') == 'ok':
        # Keep the entry ID from input to maintain tracking
        store[key]['crossref_bibtex_entry_key'] = \
            store[key]['crossref_bibtex_entry']['ID']
        store[key]['crossref_bibtex_entry']['ID'] = store[key]['input']['ID']

        status, check = double_check_bibtex_entries(
            entry, store[key]['crossref_bibtex_entry'])

        print_verbose_level(status, check)
        store[key]['check'] = check
        store[key]['found_doi_status'] = status
        if status == 'valid':
            valid_crossref_bib_db.entries.append(
                store[key]['crossref_bibtex_entry'])
    else:
        store[key]['found_doi_status'] = 'failed'

    print_verbose_level('validation results : ', store[key]['found_doi_status'],
                        '\n')
    k = k + 1

# Remove duplicate entries with the same DOI
dois = []
for key in store:
    if store[key].get('found_doi_status', '') == 'valid':
        found_doi = store[key].get('found_doi', None)
        if found_doi is not None:
            dois.append([found_doi, key])

seen = set()
duplicates = []

for x in dois:
    if x[0] in seen:
        duplicates.append(x)
    else:
        seen.add(x[0])

for d in duplicates:
    store[d[1]]['duplicate'] = True

n_duplicate_bibtex_entries = len(duplicates)

# =============================================================================
# 5. Query Unpaywall for OAI URLs
# =============================================================================
print_verbose_level(format_verbose_header.format('5. unpaywall oai from doi '))

unpaywall_oais_from_crossref_dois(valid_crossref_bib_db.entries, store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)

# =============================================================================
# 6. Build output BibTeX entries
# =============================================================================
# Merge information from Crossref and Unpaywall:
# - 'journal' is taken from Crossref
# - DOI tags and OAI tags are added
print_verbose_level(format_verbose_header.format('6. build output bibtex entry '))
ad_hoc_build_output_bibtex_entries(store)

# =============================================================================
# 7. Generate summary report
# =============================================================================
e_idx = 0

fmt_string = '# {:<6} {:<30} {:<10} {:<10} {:<40} {:<10} {:<10}'

print_verbose_level(format_verbose_header.format('7. Report'))

print_verbose_level(fmt_string.format('number',
                                      'id',
                                      'doi query',
                                      'doi',
                                      'check',
                                      'action',
                                      'unpaywall status'))
print_verbose_level(fmt_string.format('',
                                      '',
                                      '',
                                      '',
                                      '',
                                      '',
                                      'unpaywall msg'))
for key in store:
    if store[key].get('duplicate', False):
        print_verbose_level(fmt_string.format(e_idx,
                                              str(store[key]['input'].get('ID')),
                                              'duplicate',
                                              '',
                                              '',
                                              '',
                                              ''))
    else:
        print_verbose_level(fmt_string.format(e_idx,
                                              str(store[key]['input'].get('ID')),
                                              str(store[key].get('crossref_query_status')),
                                              str(store[key]['found_doi_status']),
                                              str(store[key].get('check')),
                                              str(store[key].get('action', [' '])[0]),
                                              str(store[key].get('unpaywall_status'))))
        print_verbose_level(fmt_string.format('',
                                              '',
                                              '',
                                              '',
                                              '',
                                              str(store[key].get('action', [' ', ' '])[1]),
                                              str(store[key].get('unpaywall_msg'))))
    e_idx = e_idx + 1


fmt_string_2 = '| {:<40} | {:<20} | {:<60} | {:} | {:} | {:<10} | '
print("|-")
print(fmt_string_2.format( 'Id',
                                 'found doi status',
                                 'check',
                                 'forced ',
                                 'skip' ,
                                 'comment ' ))
print("|-")
for key in store:
    entry_id = store[key]['input'].get('ID')

    test_forced =  ( entry_id in opts.forced_valid_crossref_entry)  or (entry_id in user_forced_entries)
    test_skipped =  ( entry_id in opts.skip_double_check) or (entry_id in user_skipped_entries)
    
    if store[key].get('duplicate', False):
        print(fmt_string_2.format(str(entry_id),
                                      'duplicate',
                                      '',
                                      '',
                                      '',
                                      ''))
    elif (store[key]['found_doi_status'] == '!valid')  or test_forced or test_skipped: 
        print(fmt_string_2.format( entry_id,
                                   str(store[key]['found_doi_status']),
                                   str(store[key].get('check')),
                                   bool(test_forced),
                                   test_skipped,
                                   ' ' )) 
    e_idx = e_idx + 1

print("|-")
print("\n")

    
# =============================================================================
# 8. Write output BibTeX file
# =============================================================================
print_verbose_level(format_verbose_header.format('8. Write  output bibtex file '))

edited_bib_db = BibDatabase()
for key in store:
    if store[key].get('duplicate', False):
        continue
    edited_bib_db.entries.append(store[key]['output_bibtex_entry'])

n_edited_bibtex_entries = len(edited_bib_db.entries)
print_verbose_level('## number of  entries (input) ', n_bibtex_entries)
print_verbose_level('## number of  duplicate entries (input) ',
                    n_duplicate_bibtex_entries)
print_verbose_level('## number of  entries (output) ', n_edited_bibtex_entries)

if n_edited_bibtex_entries + n_duplicate_bibtex_entries != n_bibtex_entries:
    print_verbose_level(
        '[WARNING]: The number of output entries is not same as the input',
        n_edited_bibtex_entries, '!=', n_bibtex_entries + n_duplicate_bibtex_entries)
    print_verbose_level('######## \n\n')

writer = BibTexWriter()
writer.display_order = ['author', 'title', 'journal', 'year']
with open(output_file, 'w') as bibfile:
    bibtex_str = dumps(edited_bib_db, writer)
    bibfile.write(bibtex_str)


# =============================================================================
# 9. Clean up LaTeX and HTML symbols
# =============================================================================
print_verbose_level(
    format_verbose_header.format('9. Replacements of Latex or html symbols in bibtex entries '))


def replace_curious_character(output_file):
    """
    Replace problematic characters in the output file.
    
    Fixes common LaTeX and HTML encoding issues.
    """
    text_to_replace = [('$\\mathsemicolon$', ';'),
                       ('{\\&}amp;', '\\&'),
                       ('&amp;', '\\&'),
                       ('À', '{\\`A}'),
                       ('\\i', 'i'),
                       ('–', '-'),
                       ]

    for item in text_to_replace:
        # Read the current contents of the file
        f = open(output_file, "r")
        lines = f.readlines()
        f.close()

        new_lines = []
        for line in lines:
            line_replacement = line
            if item[0] in line:
                #print('Match Found. replace ', item[0], ' by ', item[1],
                #      '  in', line)
                line_replacement = line.replace(item[0], item[1])
            new_lines.append(line_replacement)
        f = open(output_file, "w", encoding="utf-8")
        for line in new_lines:
            f.write(line)
        f.close()


replace_curious_character(output_file)


def line_prepender(filename, line):
    """Add a line at the beginning of a file."""
    with open(filename, 'r+') as f:
        content = f.read()
        f.seek(0, 0)
        f.write(line.rstrip('\r\n') + '\n' + content)


# Add header comment to output file
cartridge = \
    "@Comment{This file has been generated with the script jtcam_bibtex_editing.py}\n" + \
    "@Comment{Do not edit it directly by yourself. Modify  the source file if needed}"

line_prepender(output_file, cartridge)

import fileinput

# =============================================================================
# 10. Split output into individual files (optional)
# =============================================================================
if opts.split_output:
    print_verbose_level(format_verbose_header.format('10. Splitted bib entries'))
    list_bib_file = []
    for entry in edited_bib_db.entries:
        # Create a temporary BibTeX file for each entry
        writer = BibTexWriter()
        edited_bib = BibDatabase()
        edited_bib.entries.append(entry)
        dir_name = 'splitted_bibtex_entries'
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)

        output_file = os.path.join(dir_name, entry['ID'] + '.bib')

        str_file = r"\ "[0]
        str_file = str_file + 'addbibresource{' + output_file + '}'

        list_bib_file.append(str_file)

        with open(output_file, 'w') as bibfile:
            bibtex_str = dumps(edited_bib, writer)
            bibfile.write(bibtex_str)
        replace_curious_character(output_file)

    with open('splitted_bib_entries.tex', 'w') as f:
        for line in list_bib_file:
            f.write(f"{line}\n")

    print_verbose_level('splitted bib entries are in the folder : splitted_bibtex_entries ')
    print_verbose_level('\\input(splitted_bib_entries.tex) to use it')


# =============================================================================
# 11. Suggest command-line options based on user decisions
# =============================================================================
# Note: This section MUST be at the very end of the script
if user_forced_entries or user_skipped_entries:
    print_verbose_level(format_verbose_header.format('11. Suggested command-line options'))
    
    print("\nBased on your interactive choices, you can use these options for future runs:")
    print("\n" + "="*70)
    
    if user_forced_entries:
        forced_list = ','.join(user_forced_entries)
        print(f"\n# Force validation for these entries:")
        print(f"--forced-valid-crossref-entry={forced_list}")
    
    if user_skipped_entries:
        skipped_list = ','.join(user_skipped_entries)
        print(f"\n# Skip double-check for these entries:")
        print(f"--skip-double-check={skipped_list}")
    
    # Combined command suggestion
    print(f"\n# Combined command:")
    cmd_parts = [sys.argv[0]]
    cmd_parts.append("--forced-valid-crossref-entry --stop-on-bad-check --keep-entry= ")
    if user_forced_entries:
        cmd_parts.append(f"--forced-valid-crossref-entry={','.join(user_forced_entries)}")
    if user_skipped_entries:
        cmd_parts.append(f"--skip-double-check={','.join(user_skipped_entries)}")
    cmd_parts.append(opts.filename)
    print(" ".join(cmd_parts))
    
    print("\n" + "="*70)
