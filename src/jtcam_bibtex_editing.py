# /*
# * This simple python script uses the API of crossref and unpaywall to reformat author's bibtex file, addind verified doi and oai on open access ressources.
# * Copyright (C) 2022 Vincent Acary
# *
# * This program is free software: you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation, either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program.  If not, see <http://www.gnu.org/licenses/>.
# */


import getopt
import sys, os


import time

class TimerError(Exception):
    """A custom exception used to report errors in use of Timer class"""

class Timer:
    def __init__(self):
        self._start_time = None

    def start(self):
        """Start a new timer"""
        if self._start_time is not None:
            raise TimerError(f"Timer is running. Use .stop() to stop it")

        self._start_time = time.perf_counter()

    def stop(self):
        """Stop the timer, and report the elapsed time"""
        if self._start_time is None:
            raise TimerError(f"Timer is not running. Use .start() tos start it")

        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")


class Options(object):
    def __init__(self):
        self.filename=None
        self.verbose=0
        self.number_of_parallel_request = 5
        self.output_unpaywall_data=False
        self.skip_double_check = []
        self.forced_valid_crossref_entry = []
        self.stop_on_bad_check = False
        self.max_entry = 100000
        self.crossref_search_key =  ['author',  'year', 'title', 'journal']
        self.crossref_search_key =  ['author',  'year', 'title']
        self.use_input_crossref_doi =True
        self.keep_entry = []
    ## Print usage information
    def usage(self, long=False):
        #print(self.__doc__); print()
        print('Usage: {0} [OPTION]... <bib file>'
              .format(os.path.split(sys.argv[0])[1]))
        print()
        if not long:
            print("""[--help][--verbose][--output-unpaywall-data][--skip-double-check=][--stop-on-bad-check][--max-entry=][--keep-entry=][--forced-valid-crossref-entry=]
            """)
        else:
            print("""Options:
     --help
       display this message
     --verbose=
       set verbose
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

     """)

    def parse(self):
        ## Parse command line
        try:
            opts, args = getopt.gnu_getopt(sys.argv[1:], '',
                                           ['help', 'verbose=', 'is-oa',
                                            'output-unpaywall-data','skip-double-check=','forced-valid-crossref-entry=',
                                            'stop-on-bad-check', 'max-entry=', 'keep-entry='])
            self.configure(opts, args)

        except getopt.GetoptError as err:
            sys.stderr.write('{0}\n'.format(str(err)))
            self.usage()
            exit(2)

    def configure(self, opts, args):
        for o, a in opts:
            if o == '--help':
                self.usage(long=True)
                exit(0)
            elif o == '--verbose':
                self.verbose=int(a)
            elif o == '--output-unpaywall-data':
                self.output_unpaywall_data=True
            elif o == '--skip-double-check':
                self.skip_double_check =  a.split(',')
            elif o == '--forced-valid-crossref-entry':
                self.forced_valid_crossref_entry =  a.split(',')
            elif o == '--stop-on-bad-check':
                self.stop_on_bad_check = True
            elif o == '--max-entry':
                self.max_entry=int(a)
            elif o == '--keep-entry':
                # input_list = a.split(',')
                # self.keep_entry = {}
                # for l in range(len(input_list)//2):
                #     self.keep_entry[input_list[2*l]] = input_list[2*l+1]
                # print(self.keep_entry)
                self.keep_entry = a.split(',')
        if len(args) > 0:
            self.filename = args[0]
        else:
            self.usage()
            exit(1)

# -------------------
# for paralell job
# -------------------
from joblib import Parallel, delayed


# ----------------------
# crossref function
# ----------------------
from habanero import Crossref
from habanero import cn

# set a mailto address to get into the "polite pool"
#Crossref(mailto = "jtcam@episciences.org")



def crossref_query(bibliographic):
    print_verbose_level('crossref query search starts on {:40.40}...'.format(bibliographic))
    cr = Crossref(mailto = "jtcam@episciences.org")
    try:
        x = cr.works(query_bibliographic = bibliographic, limit=1)
    except Exception as e:
        x={}
        x['status'] = 'bad'
        print_verbose_level('exception is :', e)

    print_verbose_level('crossref query search ends on {:40.40} with status'.format(bibliographic), x['status'])
    return x

def crossref_get_doi_from_query_results(x):
    # we return the first DOI in x
    return x['message']['items'][0]['DOI']


def bibtex_entries_to_crossref_dois(store):
    print_verbose_level('Crossref doi search from bibtex input entry')
    # parrallel
    bibliographic ={}
    for key in store:
        entry = store[key]['input']
        entry_id=entry.get('ID')
        if opts.use_input_crossref_doi and entry.get('crossref_doi'):
            # we skip the search
            print_verbose_level('    use input crossref_doi for ', entry_id)
            store[key]['crossref_query_status'] = 'ok'
            store[key]['crossref_doi'] = entry.get('crossref_doi')
            continue
        else:
            if store[key].get('crossref_query_status', '') != 'ok':
                bibliographic[entry_id] =[entry]
                bibliographic[entry_id]
                query_text = []
                for key in  opts.crossref_search_key :
                    query_text.append(entry.get(key,''))
                query_text = ' '.join(query_text)
                #print('query_text', query_text)
                bibliographic[entry_id].append(query_text)
            else:
                print_verbose_level('    use cache entry for ', entry_id)
    t = Timer()
    t.start()
    if len(bibliographic) >0 :
        n_jobs= min(len(bibliographic),opts.number_of_parallel_request)
        results=Parallel(n_jobs=n_jobs)( delayed(crossref_query)(bibliographic[entry_id][1]) for entry_id in bibliographic)
    t.stop()

    cnt =0
    for entry_id in bibliographic:
        entry = bibliographic[entry_id][0]
        entry_id=entry.get('ID')
        store[entry_id]['crossref_query_status'] = results[cnt]['status']
        if results[cnt]['status'] == 'ok':
            store[entry_id]['crossref_doi'] = crossref_get_doi_from_query_results(results[cnt])

        cnt=cnt+1

import json
def doi_to_crossref_bibtex_entry(doi):

    cr = Crossref(mailto = "jtcam@episciences.org")
    print_verbose_level('crossref cn bibtex  .... for ', doi)
    #x = cr.works(query_bibliographic = bibliographic, limit=3, cursor='*', progress_bar=True)

    # x = cr.works(ids = doi)
    # print_verbose_level('crossref query search end with status', x['status'])
    # print(x)
    try:
        bibtex_entry_str=cn.content_negotiation(ids = doi, format = "bibentry")
        json_entry=cn.content_negotiation(ids = doi, format = "citeproc-json")
        #print(json_entry)
        #d = json.loads(json_entry)
        #print(d['author'])
        #print(d.keys())
        #input()
    except Exception as e:
        print('cn.content_negotiation exception', e)
        return None, None, '!ok'

    return bibtex_entry_str,json_entry, 'ok'

def dois_to_crossref_bibtex_entries(store):
    print_verbose_level('dois_to_crossref_bibtex_entries  ....')
    store_search ={}
    # list of search
    for key in store:
        #print(store[key]['crossref_query_status'])
        if store[key].get('crossref_bibtex_status', '') != 'ok':
             store_search[key] =store[key]
        else:
            print_verbose_level('   use cache for ', store[key]['input']['ID'])

    t = Timer()
    t.start()
    if len (store_search) >0 :
        n_jobs= min(len(store_search),opts.number_of_parallel_request)
        results=Parallel(n_jobs=n_jobs)( delayed(doi_to_crossref_bibtex_entry)(store[key]['crossref_doi']) for key in store_search)
    t.stop()
    cnt = 0
    for key in store_search:
        bibtex_entry_str,json_entry, status  = results[cnt]
        store[key]['crossref_bibtex_status'] = status
        if status == 'ok':
            store[key]['crossref_json_entry']=json_entry
            #print(bibtex_entry_str)
            bp = BibTexParser(interpolate_strings=False)
            bib_database = bp.parse(bibtex_entry_str)
            for e in bib_database.entries: # to be improved
                store[key]['crossref_bibtex_entry']  = e
                break
        cnt =cnt+1


# ----------------------
# unpaywall function
# ----------------------
#https://pypi.org/project/unpywall/

from unpywall.utils import UnpywallCredentials
UnpywallCredentials('vincent.acary@inria.fr')
from unpywall import Unpywall

def unpywall_query(title, is_oa):

    try:
        query = Unpywall.query(query=title, is_oa=is_oa, errors='ignore')
        if query is not None:
            # for k in query.keys():
            #     print(query[k])
            msg =  '{Unpywall.query on title returns results with is_oa='+ str(is_oa) +  '}'
            print_verbose_level(msg)
            status = 'query ok'
        else:
            # print(type(query), query)
            msg =  '{Unpywall.query on title  returns None with is_oa='+ str(is_oa) +  '}'
            print_verbose_level(msg)
            status = 'query none'

    except Exception as e :
        query=None
        msg = '[warning]: Unpywall.query on title on unpaywall failed !!!'+ e
        print_verbose_level(msg)
        status = 'not found'
        input()
    return query, msg, status


def unpywall_doi(doi):
    try:
        query = Unpywall.doi(dois=[doi],  errors='ignore') # progress=True
        #doi_query = Unpywall.query(query=doi_query['doi'][0], is_oa=True)
        #print(doi_query)
        if query is not None:
            msg =  '{Unpywall.doi returns results}'
            # for k in query.keys():
            #     print(query[k])
            status = 'doi found'
        else:
            # print(type(query), query)
            print_verbose_level('[error]: doi query on unpaywall is None !!!')
            msg =  '{Unpywall.doi returns None}'
            status = 'doi not found'

    except Exception as e :
        print_verbose_level('[warning]: Unpywall.doi  failed !!!', e)
        msg =  '{Unpywall.doi failed}' +e
        status = 'doi failed'

    return query, msg, status


def unpaywall_get_oai_url(doi_query):
    oai_url='oai url not found'
    status='oai url not found'

    if doi_query.get('best_oa_location.url_for_pdf') is not None:
        if doi_query['best_oa_location.url_for_pdf'][0] is not None:
            oai_url=urllib.parse.unquote(doi_query['best_oa_location.url_for_pdf'][0],  errors='replace')
            status='oai url found'
            print_verbose_level('unpaywall oai url:', oai_url)

    if doi_query.get('best_oa_location.url') is not None:
        if doi_query.get('best_oa_location.url')[0] is not None:
            oai_url=urllib.parse.unquote(doi_query['best_oa_location.url'][0],  errors='replace')
            status='oai url found'
            print_verbose_level('unpaywall oai url:', oai_url)

    if doi_query.get('best_oa_location.url_for_landing_page') is not None:
        if doi_query.get('best_oa_location.url_for_landing_page')[0] is not None:
            oai_url=urllib.parse.unquote(doi_query['best_oa_location.url_for_landing_page'][0],  errors='replace')
            status='oai url found'
            print_verbose_level('unpaywall oai url:', oai_url)

    return oai_url, status

def unpaywall_oais_from_crossref_dois(entries,store):



    t = Timer()
    t.start()
    results=Parallel(n_jobs=len(entries))(delayed(unpywall_doi)(store[entry.get('ID')]['crossref_doi']) for entry in entries)
    t.stop()

    cnt = 0
    for entry in entries:
        doi_query, unpaywall_msg, unpaywall_status = results[cnt]

        store[entry.get('ID')]['unpaywall_msg'] =  unpaywall_msg
        store[entry.get('ID')]['unpaywall_status'] =  [unpaywall_status]

        if doi_query is not None :

            if opts.output_unpaywall_data:
                doi_query_dict= doi_query.to_dict('dict')
                print(doi_query_dict)
                store[entry.get('ID')]['unpaywall_data'] =json.dumps(doi_query_dict, indent=4)

            if unpaywall_status == 'doi found':
                oai_url, status  = unpaywall_get_oai_url(doi_query)
                store[entry.get('ID')]['oai_url']=  oai_url
                store[entry.get('ID')]['unpaywall_status'].append(status)

                # test if OAI is arviv or hal
                oai_host_type=None
                oai_repository_institution=None

                if doi_query.get('best_oa_location.host_type') is not None:
                    oai_host_type= doi_query.get('best_oa_location.host_type')[0]
                if doi_query.get('best_oa_location.repository_institution') is not None:
                    oai_repository_institution= doi_query.get('best_oa_location.repository_institution')[0]

                if (oai_host_type == 'repository') and (oai_repository_institution is not None):
                    if 'arXiv' in oai_repository_institution:
                        print(doi_query)
                        store[entry.get('ID')]['oai_url_for_landing_page'] = doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print('landing: ',store[entry.get('ID')]['oai_url_for_landing_page'])
                        store[entry.get('ID')]['oai_type']=  'arXiv'
                        #input()
                    if 'HAL' in oai_repository_institution:
                        store[entry.get('ID')]['oai_type']=  'HAL'
                        store[entry.get('ID')]['oai_url_for_landing_page'] = doi_query.get('best_oa_location.url_for_landing_page')[0]
                        print('landing: ',store[entry.get('ID')]['oai_url_for_landing_page'])

                    # if 'CiteSeer' in oai_repository_institution:
                    #     store[entry.get('ID')]['oai_type']=  'CiteSeer'
                #print (oai_host_type, oai_repository_institution)
                #input()

        cnt= cnt+1


def double_check_bibtex_entries(input_bibtex_entry, crossref_bibtex_entry):

    #print(opts.skip_double_check)
    #print(input_bibtex_entry.get('ID'))
    flag_skip = input_bibtex_entry.get('ID') in opts.skip_double_check

    flag_forced_valid= input_bibtex_entry.get('ID') in opts.forced_valid_crossref_entry

    check= ''
    flag=True

    # ------------------------------
    # -------- check input_bibtex_entry type
    #  (useful for same title and year for a conference and journal publication )
    # ------------------------------

    if input_bibtex_entry.get('ENTRYTYPE') != crossref_bibtex_entry.get('ENTRYTYPE')  :
        check += 'entry type: !ok '
        flag= flag and False
        print_verbose_level('[Warning] input_bibtex_entry type are different.', input_bibtex_entry.get('ENTRYTYPE'), crossref_bibtex_entry.get('ENTRYTYPE'))
        # if opts.stop_on_bad_check and not flag_skip:
        #     print_verbose_level('press a key to continue')
        #     input()


    # ------------------------------
    # -------- check year
    # ------------------------------
    year_1_text = input_bibtex_entry.get('year', '')
    year_2_text = crossref_bibtex_entry.get('year', '')

    if year_1_text !=  year_2_text and year_2_text != '':
        check += 'year: !ok '
        flag= flag and False
        print_verbose_level('[Warning] years are different.\n year in input bibtex :', year_1_text, '\n year crossref bibtex :', year_2_text)
        # if opts.stop_on_bad_check and not flag_skip:
        #     print_verbose_level('press a key to continue')
        #     input()
    elif year_2_text == '':
        check += 'year: none(2)'
    elif year_1_text == '':
        check += 'year: none(1)'
    else:
        check += 'year: ok '

    # ------------------------------
    # -------- check title
    # ------------------------------

    document_1_text = input_bibtex_entry.get('title', '').lower().replace('{','').replace('}','')
    document_2_text = crossref_bibtex_entry.get('title', '').lower().replace('{','').replace('}','')
    document_2_text = document_2_text.replace('\\textquotesingle','\'').replace('\\textendash', '--').replace('\\textemdash','-')


    document_1_words = document_1_text.split()
    document_2_words = document_2_text.split()
    common = set(document_1_words).intersection( set(document_2_words) )
    intersection = set(document_1_words).symmetric_difference( set(document_2_words) )
    #input()
    if len(intersection) < 1 :
        check += 'title: ok+ '
        flag = flag and True
    elif len(intersection) < 3 :
        check += 'title: ok- '
        flag = flag and True
        #print(common, intersection)
        print_verbose_level('[Warning] small difference in title', intersection)
    else:
        check += 'title: !ok '
        flag = flag and False
        if opts.stop_on_bad_check and not flag_skip:
            print_verbose_level('[Warning] title in input bibtex:\n', document_1_text, '\n')
            print_verbose_level('[Warning] title in crossref bibtex:\n', document_2_text, '\n')
            print('difference: ', intersection, len(intersection))
            # print_verbose_level('error: large difference in title', intersection)
            # print_verbose_level('press a key to continue')
            # input()

    # ------------------------------
    # -------- check other author ?
    # ------------------------------
    # todo


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

        print_verbose_level('hints: you may manually add crossref_doi ={foo} in the input entry of the bibtex file to fix the issue ')
        if  opts.stop_on_bad_check and not flag_skip and not flag_forced_valid:
            print_verbose_level('press a key to continue')
            input()


    if flag :
        status = 'valid'
    else:
        status = '!valid'

    if  flag_skip:
        status = 'skipped'


    if  flag_forced_valid:
        status = 'valid'
        check += 'forced valid'

    return status,  check

import json
import urllib # to have url complient with  Latex


def add_tag_doi_in_entry(doi, entry):

    entry['crossref_doi'] = doi

    if entry.get('addendum_item'):
        entry['addendum_item'].append('\\tagDOI{' + entry['crossref_doi'] + '}')
    else:
        entry['addendum_item']= ['\\tagDOI{' + entry['crossref_doi'] + '}']

    return 'add doi'

def add_tag_oai_url_in_entry(store_key, entry):

    oai_url = store_key['oai_url']
    entry['unpaywalloaiurl'] = oai_url
    latex_tag = None

    if  store_key.get('oai_type') == 'arXiv':
        latex_tag='\\tagARXIV{'
        oai_url = store_key['oai_url_for_landing_page']
        print(oai_url)
    elif store_key.get('oai_type') == 'HAL':

        fake_landing_page=  store_key['oai_url_for_landing_page']
        #print('fake_landing_page', fake_landing_page)
        fake_landing_page_split = fake_landing_page.split('/')
        # if len(fake_landing_page_split) > 1  :
        #     #print(fake_landing_page_split)
        #     for e in reversed(fake_landing_page_split):
        #         if e[:4] == 'hal-':
        #             oai_url = e
        #             break
        #     #hal_number = fake_landing_page.split('hal-')[1].split('/')[0]
        #     #oai_url = 'hal-' + hal_number
        #     #print(oai_url)
        #     #input()
        #     latex_tag='\\tagHAL{'
        # else:
        #     print('no hal number')
        #     latex_tag = '\\tagOAI{'
        #     oai_url = fake_landing_page
        #     print(oai_url)
        latex_tag='\\tagHAL{'
        oai_url = store_key['oai_url_for_landing_page']
    else:
        latex_tag='\\tagOAI{'

    if latex_tag is not None:
        if entry.get('addendum_item'):
            entry['addendum_item'].append(latex_tag +  oai_url+ '}')
        else:
            entry['addendum_item']= [latex_tag +  oai_url + '}']


    return 'add oai'

def complete_addendum_in_entry(entry):

    if  entry.get('addendum'):
        print('keep input addendum as it is', addendum)
        input()
    elif  entry.get('addendum_item'):
        entry['addendum'] =  ', '.join(entry['addendum_item'])
        entry.pop('addendum_item')


def astyle_author_crossref_bibtex(crossref_author):
    author_list = crossref_author.split(' and ')
    new_author_list =[]
    for a in author_list:
        #print(a)
        ll = a.split(' ')
        lastname = ll.pop().lower()
        firstname = ' '.join(ll).lower()
        new_author_list.append(lastname.title() + ', ' + firstname.title())
        #print(new_author_list[-1])
    author_bibtex = ' and ' .join(new_author_list)
    #print('author_bibtex', author_bibtex)
    return author_bibtex

def astyle_author_crossref_json(json_entry):
    d = json.loads(json_entry)
    author=d['author']
    #print(author)
    author_bibtex =[]


    for a in author:

        family = a['family']
        if family.isupper():
            family = family.title()

        if a.get('given', None) :
            given = a['given']
            author_bibtex.append(family+ ', ' +given)
        else:
            author_bibtex.append(family)

    author_bibtex = ' and ' .join(author_bibtex)
    #print('author_bibtex', author_bibtex)
    return author_bibtex




def ad_hoc_build_output_bibtex_entries(store):
    print_verbose_level('ad_hoc_build_output_bibtex_entries')

    k=0
    for key in store:

        if store[key].get('duplicate', False) :
            continue

        input_bibtex_entry=store[key]['input']

        if  store[key].get('crossref_bibtex_status', '') != 'ok':
            store[key]['output_bibtex_entry']=input_bibtex_entry
            continue


        crossref_bibtex_entry=store[key]['crossref_bibtex_entry']
        print_verbose_level('## input_bibtex_entry ', k ,': ', input_bibtex_entry.get('ID'))


        writer = BibTexWriter()
        db = BibDatabase()
        db.entries.append(input_bibtex_entry)
        db.entries.append(crossref_bibtex_entry)
        print(writer.write(db))

        store[key]['action'] = ['','']

        # start from base_entry

        store[key]['output_bibtex_entry']=input_bibtex_entry
        output_bibtex_entry=store[key]['output_bibtex_entry']

        if not (input_bibtex_entry['ID']  in opts.skip_double_check):

            if store[key]['crossref_doi_status'] == 'valid' :

                #use_entry = ['journal', 'author', 'title',
                #            'publisher', 'volume', 'number', 'booktitle', 'pages']
                use_entry = ['journal', 'author',
                            'publisher', 'volume', 'number', 'booktitle', 'pages']

                for i in range(len(opts.keep_entry)):
                    if opts.keep_entry[i] == entry['ID'] :
                        if opts.keep_entry[i+1] in use_entry:
                            use_entry.remove(opts.keep_entry[i+1])

                #print(use_entry)

                for bkey in use_entry:
                    if crossref_bibtex_entry.get(bkey):
                        if bkey == 'author':
                            #print(crossref_bibtex_entry.get(bkey))
                            output_bibtex_entry[bkey]= astyle_author_crossref_bibtex(crossref_bibtex_entry.get(bkey))
                            output_bibtex_entry[bkey]= astyle_author_crossref_json(store[key]['crossref_json_entry'])
                        else:
                            output_bibtex_entry[bkey]= crossref_bibtex_entry[bkey]

                #output_bibtex_entry['journal']= crossref_bibtex_entry['journal']
                store[key]['action'] [0] = add_tag_doi_in_entry(store[key]['crossref_doi'], output_bibtex_entry)

                if store[key]['unpaywall_status'][1] == 'oai url found' :
                    #output_bibtex_entry['year']= crossref_bibtex_entry['journal']
                    #output_bibtex_entry['journal']= crossref_bibtex_entry['journal']
                    store[key]['action'] [1] = add_tag_oai_url_in_entry(store[key], output_bibtex_entry)

                complete_addendum_in_entry(output_bibtex_entry)


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


#        if output_bibtex_entry.get('isbn'):
#            print('isbn', output_bibtex_entry.get('isbn'))

                
        # writer = BibTexWriter()
        # db = BibDatabase()
        # db.entries.append(entry)
        # db.entries.append(crossref_bibtex_entry)
        # db.entries.append(output_bibtex_entry)
        # print(writer.write(db))

        # intersection = set(entry.keys()).symmetric_difference( output_bibtex_entry.keys() )
        # if 'addendum' in intersection:
        #     intersection.remove('addendum')
        # if 'unpaywall_doi'in intersection:
        #     intersection.remove('unpaywall_doi')
        # if 'unpaywalloaiurl'in intersection:
        #     intersection.remove('unpaywalloaiurl')
        # print(intersection)

        # for k in intersection:
        #     if entry.get(k):
        #         output_bibtex_entry[k] = entry.get(k)



        k= k+1



# ------------------------------
# -------- main part
# -------------------------------

opts = Options()
opts.parse()

verbose_level = 1

def print_verbose_level(*args, **kwargs):
    if verbose_level:
        print('[jtcam unpaywall]', *args, **kwargs)

base_filename =  os.path.splitext(opts.filename)[0]
if os.path.exists(opts.filename):
    output_file = base_filename+'_edited.bib'
else:
    print_verbose_level('bib file', opts.filename, 'is not existing')
    exit(0)

#file='../../PAPERS/2021_Mar_6906/Biblio_Corre2020_JTCAM.bib'

# -------- bibtex parsing start
# 1. Parsing of the bibtex entry with `bibtexparser`
# -------- bibtex parsing end

format_verbose_header = ' '+'-'*42  +'------------------------------------------------#\n'+  ' '*18 + ' {:<40}  ------------------------------------------------#'
print_verbose_level(format_verbose_header.format('1. Parse input bibtex file'))



from bibtexparser import load, dumps
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase, as_text
with open(opts.filename) as bibtex_file:
    # old way
    #bib_database = load(bibtex_file)

    bibtex_str = bibtex_file.read()
    #we use the option interpolate_strings=False foo string that are not defined
    bp = BibTexParser(interpolate_strings=False)
    bib_database = bp.parse(bibtex_str)


n_bibtex_entries = len(bib_database.entries)

# for entry in bib_database.entries:
#     entry_id = entry.get('ID')
#     print('entry_id', entry_id)


print_verbose_level('# number of  entries (input) ', n_bibtex_entries)
# input()

bib_database.entries = bib_database.entries[:opts.max_entry]


# -------- bibtex parsing end


# We build a store dictionnary for collecting
# - input entry
# - output entry
# - crossref entry
# - extra info on query, doi, oai, ....


import pickle

pickle_name = base_filename + '_cache.pickle'

if os.path.exists(pickle_name):
    #print('open pickle file')
    with open(pickle_name, 'rb') as handle:
        store = pickle.load(handle)
else:
    store = {}

# remove entry in store that is no longer in bib input file
current_entries= [entry.get('ID') for entry in bib_database.entries]
entry_to_pop = []
for entry in store:
    print(entry)
    if entry not in current_entries:
        print('entry in cache ', entry,' no longer in input bibtex file')
        entry_to_pop.append(entry)
for e in entry_to_pop:
    store.pop(e)

for entry in bib_database.entries:
    entry_id = entry.get('ID')
    dict_entry = store.get(entry_id, {})
    if dict_entry == {} :
        store[entry_id] = {}
        store[entry_id]['input'] = entry
    else:
        # compare dict_entry['input'] with entry
        if dict_entry['input'] == entry :
            print_verbose_level('    entry' , entry_id,' has not changed. we use cache information')
        else:
            store[entry_id] = {}
            store[entry_id]['input'] = entry
            print_verbose_level('    entry' , entry_id,' has changed. cache is removed')




# 2. Crossref doi search with the crossref API using habanero.
#    the most relevent doi is stored in `crossref_doi`
#    - we use it to do a query on crossref with the ['author', 'title', 'year', 'journal'] of the bibtex entry
#    - we do not use the input key `doi` since we do not want it in the final key `doi`
# 	   if the author set the key `doi`, rename it as `crossref_doi`
#   - the doi can be set in the input file in `crossef_doi`. In that case, the Crossref doi search is not done
print_verbose_level(format_verbose_header.format('2. Crossref doi seach'))

bibtex_entries_to_crossref_dois(store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)



# 3. bibtex entry query on Crossref using `crossref_doi` 
#   - A bibtex entry is requested to Crossref from `crossref_doi`

print_verbose_level(format_verbose_header.format('3. get bibtex from crossef '))


dois_to_crossref_bibtex_entries(store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)


# 4. Validation of the crossref bibtex entry
#  - the validation is based on year title author ad entry type.
#  - for valid ntries, we remove duplicate (entries with the same valid DOIs)
print_verbose_level(format_verbose_header.format('4. validation of crossref_bibtex_entry '))

k=0
valid_crossref_bib_db=BibDatabase()
for key in store:
    entry = store[key]['input']
    check = '--'
    print_verbose_level('## entry ', k ,': ', entry.get('ID'))

    if store[key].get('crossref_bibtex_status', '') == 'ok':
        # keep the entry ID of the input to keep track

        store[key]['crossref_bibtex_entry_key'] = store[key]['crossref_bibtex_entry']['ID']
        store[key]['crossref_bibtex_entry']['ID'] = store[key]['input']['ID']

        status, check = double_check_bibtex_entries(entry, store[key]['crossref_bibtex_entry'])

        print_verbose_level(status, check)
        store[key]['check']= check
        store[key]['crossref_doi_status'] =status
        if status == 'valid':
            valid_crossref_bib_db.entries.append(store[key]['crossref_bibtex_entry'])
    else:
        store[key]['crossref_doi_status'] = 'failed'


    print_verbose_level('validation results : ', store[key]['crossref_doi_status'], '\n')

    k=k+1

#  - we remove duplicate of valid entries with the same DOI
dois = []
for key in store:
    #print('key',store[key]['crossref_doi'])
    if store[key].get('crossref_doi_status', '') == 'valid':
        crossref_doi = store[key].get('crossref_doi', None)
        if crossref_doi is not None:
            dois.append([crossref_doi,key])

#print(dois)

seen = set()
duplicates = []

for x in dois:
    if x[0] in seen:
        duplicates.append(x)
    else:
        seen.add(x[0])
#print(duplicates)

for d in duplicates:
    #print('entry', d[1], 'is duplicate. We do not treat it')
    store[d[1]]['duplicate'] = True
    #store.pop(d[1])

n_duplicate_bibtex_entries = len(duplicates)

#input()






    

# 5. We use the validated  `crossref_doi`  to make oai query on Unpaywall
print_verbose_level(format_verbose_header.format('5. unpaywall oai from doi '))
unpaywall_oais_from_crossref_dois(valid_crossref_bib_db.entries, store)

with open(pickle_name, 'wb') as handle:
    pickle.dump(store, handle, protocol=pickle.HIGHEST_PROTOCOL)

# 6. We try to merge at best info from crossref and unpaywall
#   - `journal` is taken from crossref
#   - ....

print_verbose_level(format_verbose_header.format('6. build output bibtex entry '))
ad_hoc_build_output_bibtex_entries(store)


# summary
e_idx=0

fmt_string =  '# {:<6} {:<30} {:<10} {:<10} {:<40} {:<10} {:<10}'

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

    if store[key].get('duplicate', False) :
        print_verbose_level(fmt_string.format(e_idx,
                                              str(store[key]['input'].get('ID')),
                                              'duplicate',
                                              '',
                                              '',
                                              '',
                                              ''
                                              )
                            )


    else:
        print_verbose_level(fmt_string.format(e_idx,
                                              str(store[key]['input'].get('ID')),
                                              str(store[key].get('crossref_query_status')),
                                              str(store[key]['crossref_doi_status']),
                                              str(store[key].get('check')),
                                              str(store[key].get('action',[' '])[0]),
                                              str(store[key].get('unpaywall_status'))
                                              )
                            )
        print_verbose_level(fmt_string.format('',
                                              '',
                                              '',
                                              '',
                                              '',
                                              str(store[key].get('action', [' ', ' '])[1]),
                                              str(store[key].get('unpaywall_msg'))
                                              )
                            )

    # keep_copy_editing = True
    # if keep_copy_editing :
    #     output_bibtex_entry['action'] = ' '.join(output_bibtex_entry['action'])
    #     if  output_bibtex_entry.get('unpaywall_status'):
    #         output_bibtex_entry['unpaywall_status'] = ' '.join(output_bibtex_entry['unpaywall_status'])
    # else:
    #     output_bibtex_entry.pop('crossref_doi_status')
    #     output_bibtex_entry.pop('crossref_query_status')
    #     if  output_bibtex_entry.get('unpaywall_msg'):
    #         output_bibtex_entry.pop('unpaywall_msg')
    #     if  output_bibtex_entry.get('unpaywall_status'):
    #         output_bibtex_entry.pop('unpaywall_status')

    #     output_bibtex_entry.pop('check')
    #     output_bibtex_entry.pop('action')

    e_idx=e_idx+1
#     if e_idx >= opts.max_output_bibtex_entry:
#         break


print_verbose_level(format_verbose_header.format('8. Write  output bibtex file '))


edited_bib_db=BibDatabase()
for key in store:
    if store[key].get('duplicate', False) :
        continue
    edited_bib_db.entries.append(store[key]['output_bibtex_entry'])

n_edited_bibtex_entries = len(edited_bib_db.entries)
print_verbose_level('## number of  entries (input) ', n_bibtex_entries)
print_verbose_level('## number of  duplicate entries (input) ', n_duplicate_bibtex_entries)
print_verbose_level('## number of  entries (output) ', n_edited_bibtex_entries)

if n_edited_bibtex_entries + n_duplicate_bibtex_entries != n_bibtex_entries :
    print_verbose_level('[WARNING]: The number of output entries is not same as the input', n_edited_bibtex_entries, '!=', n_bibtex_entries + n_duplicate_bibtex_entries)
    print_verbose_level('######## \n\n')


writer = BibTexWriter()
#writer.contents = ['comments', 'entries']
#writer.indent = '  '
#writer.order_entries_by = ('ENTRYTYPE', 'author', 'year')
writer.display_order=['author','title','journal', 'year']
with open(output_file, 'w') as bibfile:
    bibtex_str = dumps(edited_bib_db, writer)
    bibfile.write(bibtex_str)



def line_prepender(filename, line):
    with open(filename, 'r+') as f:
        content = f.read()
        f.seek(0, 0)
        f.write(line.rstrip('\r\n') + '\n' + content)


cartrigde = \
"@Comment{This file has been generated with the script jtcam_bibtex_editing.py}\n" + \
"@Comment{Do not edit it directly by yourself. Modify  the source file if needed}"

line_prepender(output_file, cartrigde)

import fileinput


# 7. Some replacements are made to avoid curious Latex or html symbols in bibtex entries

text_to_replace =[('$\mathsemicolon$', ';'),('{\&}amp;', '\&')]

for item in text_to_replace:
    tempFile = open( output_file, 'r+' )
    for line in fileinput.input( output_file ):
        if item[0] in line :
            print('Match Found. replace ', item[0], ' by ', item[1])
        #else:
        #    print('Match Not Found!!')
        tempFile.write( line.replace( item[0], item[1] ) )
    tempFile.close()



#r = Unpywall.doi(dois=['10.1038/nature12373', '10.1093/nar/gkr1047'])


#print(r)
