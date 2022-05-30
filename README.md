# Python script jtcam_bibtex_editing

Vincent Acary

This simple pyhton script uses the API of crossref and unpaywall to reformat author's bibtex file, addind verified doi and oai on open access ressources.

The script is experimental and must be improved.

Licence :  GPLv3

# How to run:

```shell
python jtcam_bibtex_editing.py test.bib
```


## Search strategy

1. Parsing of the bibtex entry with `bibtexparser`
  - we use the option interpolate_strings=False for string that are not defined  
2. If `unpaywall_doi` is not a key of the bibtext entry
    - we use it to do a query on crossref with the ['author', 'title', 'year', 'journal'] of the bibtex entry
	- we select the most relevant item
	- we convert this item in bibtex format into  `crossref_bibtex_entry`
	- we check that this item relevant with author data
	- we keep the doi and we store it in the key `unpaywall_doi` of `crossref_bibtex_entry`
3. If `unpaywall_doi` is a key of the bibtext entry
	- we use it to do a doi search on crossref 
	- we convert this item in bibtex format into  `crossref_bibtex_entry`
	- we check that this item relevant with author data
	- we keep the doi and we store it in the key `unpaywall_doi` of `crossref_bibtex_entry`
4. We use the key  `unpaywall_doi` of `crossref_bibtex_entry` to make doi request on Unpaywall
   -   We do no longer  use the key `doi` since we do not want it in the final key `doi`
	   if the author set the key `doi`, rename it as `unpaywall_doi`
5. We check again the validity of the result (this should be optional)
6. We build the output bibtex entry with the `\\tag` using the key `unpaywall_doi` and `unpaywall_oai_url`. The key `unpaywall_oai_url` is set
7. We try to merge at best info from crossref and unpaywall
   - `journal` is taken from crossref
   - ,,,
