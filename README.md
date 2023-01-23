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
2. Crossref doi search with the crossref API using habanero.
   the most relevent doi is stored in `crossref_doi`
   - we use it to do a query on crossref with the ['author', 'title', 'year', 'journal'] of the bibtex entry
   - we do not use the input key `doi` since we do not want it in the final key `doi`
	   if the author set the key `doi`, rename it as `crossref_doi`
   - the doi can be set in the input file in `crossef_doi`. In that case, the Crossref doi search is not done
3. bibtex entry query on Crossref using `crossref_doi` 
   - A bibtex entry is requested to Crossref from `crossref_doi`   
4. Validation of the crossref bibtex entry
   - the validation is based on year title author ad entry type.   
   - for valid ntries, we remove duplicate (entries with the same valid DOIs)
5. We use the validated  `crossref_doi`  to make oai query on Unpaywall
6. We try to merge at best info from crossref, unpaywall and input entry
   - `journal` is taken from crossref
   - ....
7. Some replacements are made to avoid curious Latex or html symbols in bibtex entries
