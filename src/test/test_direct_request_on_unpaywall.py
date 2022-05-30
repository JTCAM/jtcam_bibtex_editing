import requests

url='https://api.unpaywall.org/my/request?email=vincent.acary@inrialpes.fr'
url='https://unpaywall.org/products/api#get-doi'
# if resp.status_code != 200:
#     # This means something went wrong.
#     print(' something went wrong.')
#     raise requests.ApiError('GET /v2/search?query=:your_query[&is_oa=boolean]')
#     #print('{} {}'.format(todo_item['id'], todo_item['summary']))


# try:
#     r = requests.get('http://www.google.com/nothere')
#     r.raise_for_status()
# except requests.exceptions.HTTPError as err:
#     raise SystemExit(err)


try:
    #r, u = requests.get(url, params={'GET /v2/search?query=:your_query[&is_oa=boolean]'})
    response = requests.get(url, params={'GET /v2/search?query=:your_query[&is_oa=boolean]'}) 
    print('response', response)
    if response.status_code != 200:
         #This means something went wrong.
         print(' something went wrong.')
    
except requests.exceptions.Timeout:
    # Maybe set up for a retry, or continue in a retry loop
    pass
except requests.exceptions.TooManyRedirects:
    # Tell the user their URL was bad and try a different one
    pass
except requests.exceptions.RequestException as e:
    # catastrophic error. bail.
    raise SystemExit(e)


for todo_item in response.json():
    print(todo_item)
