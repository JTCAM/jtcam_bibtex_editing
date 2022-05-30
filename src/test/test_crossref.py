
from habanero import Crossref

# set a mailto address to get into the "polite pool"
Crossref(mailto = "vincent.acary@inria.fr")

cr = Crossref()
doi_of_interest = '10.1023/A:1008774529556'


#Works route

# query
#x = cr.works(query = "ecology")
#print(x['message'])
#print(x['message']['total-results'])
#print(x['message']['items'])


# fetch data by DOI
#cr.works(ids = '10.1371/journal.pone.0033693')

print(cr.works(ids = doi_of_interest))

# fetch data by entry


bibliographic = '"The Sweeping Processes without Convexity"' + "Colombo" + "Set-Valued Analysis volume" +"1999"
bibliographic =  "'Set-Valued Analysis volume'" +"1999"
author = "Colombo" + " Goncharov"
bibliographic += author 

#cr.works(filter = {'award_number': 'CBET-0756451', 'award_funder': '10.13039/100000001'})

x = cr.works(query_bibliographic = bibliographic, query_author=author, limit=3, progress_bar=True )
#print('\n########', x, len(x))
#input()

# Parse output to various data pieces
#x = cr.works(filter = {'has_full_text': True})

## get doi for each item
print([ z['DOI'] for z in x['message']['items'] ])

## get doi and url for each item
print([ {"doi": z['DOI'], "url": z['URL']} for z in x['message']['items'] ])

from habanero import cn
### print every doi
for i in x['message']['items']:
     print(i['DOI'])
     bibtex_entry=cn.content_negotiation(ids = i['DOI'], format = "bibentry")
     print(bibtex_entry)
     # we select the most relevant
     doi_of_interest = i['DOI']
     break
     
# for e in x['message']['items']:
#     print(e)
#     input()
#     # doi_of_interest = e['doi']
#     # bibtex_entry=cn.content_negotiation(ids = doi_of_interest, format = "bibentry")
#     # print(bibtex_entry)


#input()


#Members route

# ids here is the Crossref Member ID; 98 = Hindawi
# cr.members(ids = 98, works = True)


# Citation counts

#from habanero import counts
#print('number_of_citation', counts.citation_count(doi = doi_of_interest))


#Content negotiation - get citations in many formats
doi_of_interest = '10.1093/qjmam/45.4.575'
from habanero import cn
# cn.content_negotiation(ids = '10.1126/science.169.3946.635')
# cn.content_negotiation(ids = '10.1126/science.169.3946.635', format = "citeproc-json")
# cn.content_negotiation(ids = "10.1126/science.169.3946.635", format = "rdf-xml")
# cn.content_negotiation(ids = "10.1126/science.169.3946.635", format = "text")
# cn.content_negotiation(ids = "10.1126/science.169.3946.635", format = "text", style = "apa")
print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "apa"))
print(cn.content_negotiation(ids = doi_of_interest, format = "bibentry", style = "apa"))

doi_of_interest = '10.1093/qjmam/45.4.575'
bib_apa = cn.content_negotiation(ids = doi_of_interest, format = "text", style = "apa")
print(bib_apa)

author = bib_apa.split('(')[0].replace(', &',' and ')
print(author)
print(cn.content_negotiation(ids = doi_of_interest, format = "bibentry", style = "apa"))



#print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "harvard3"))
#print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "elsevier-harvard"))
#print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "ecoscience"))
#print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "heredity"))
#print(cn.content_negotiation(ids = doi_of_interest, format = "text", style = "oikos"))

#print(cn.csl_styles())
