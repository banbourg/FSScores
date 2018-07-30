#!/bin/env python

import requests
from bs4 import BeautifulSoup
import urllib.request, urllib.error, urllib.parse
import os
import re


# STEP 1: Find links to all event pages since ISU website is not mappable
start_year = 2004
search_events = ['russia', 'france', 'america', 'canada', 'europeans', 'wtt', 'china', 'nhk', 'russia', 'france', 'america', 'canada', 'GPF', 'continents', 'olympic', 'world'] #'bompard', 'china', 'nhk',
event_dic = {'nhk': 'NHK', 'france': 'TDF', 'canada': 'SC', 'russia': 'COR', 'america': 'SA', 'china': 'COC',
             'GPF': 'GPF', 'world': 'WC', 'continents': '4CC', 'olympic': 'OWG', 'wtt': 'WTT', 'europeans': 'EC',
             'bompard': 'TDF'}
isu_names = {'NHK': 'gpjpn', 'TDF': 'gpfra', 'SC': 'gpcan', 'COR': 'gprus', 'SA': 'gpusa', 'COC': 'gpchn',
             'GPF': 'gpf', 'WC': 'wc', '4CC': 'fc', 'OWG': 'owg', 'WTT': 'wtt', 'EC': 'ec'}
google_link_list = []
h2_events = ['WC', 'WTT', '4CC', 'OWG', 'EC']

for search_event in search_events:
    search_year = start_year
    while search_year < 2005:

        # print 'EVENT & YEAR: '

        search = 'https://www.google.co.uk/search?q=isu+results+' + search_event + '+' + str(search_year)
        r = requests.get(search)
        html = BeautifulSoup(r.text, "html.parser")
        all_links = html.find_all('cite')

        # SET SEASON
        if event_dic[search_event] not in h2_events:
            season = 'SB' + str(search_year)
        else:
            season = 'SB' + str(search_year - 1)

        print(search_event, search_year, season)

        for link in all_links:
            if "isuresults" in str(link):  # and "season" in str(link):
                google_link_list.append((event_dic[search_event], search_year, season, link.text))
                break
        search_year += 1

print(google_link_list)

# STEP 2: On each page, locate the 4 singles scoring pdfs and download them
pdf_link_list = []
disciplines = {'Danc': 'Dance', 'Pairs': 'Pairs', '0403': 'Dance', '0405': 'Dance', '0303': 'Pairs', '0305': 'Pairs'} #['Ladies', 'Men']
dir_path = os.path.expanduser('~/Desktop/bias/pdfs_with_check/pairs_id/')

for (event, year, season, link) in google_link_list:

    print(event, year, season, link)

    response = requests.get('http://'+link, stream=True)
    event_page = BeautifulSoup(response.text, "html.parser")
    isu_name = isu_names[event]

    if event in h2_events:
        right_year = str(int(season[-4:]) + 1)
    else:
        right_year = season[-4:]

    print(event, right_year)

    # Check that the top google result is for the right hear (avoids 'OWG 2016' search returning pyeongchang)
    # Note: Using the google search method bc url construction is not uniform over time.
    if isu_name in link and (right_year in link or str(year)[-2:] in link):
        for sublink in event_page.find_all('a'):
            url = sublink.get('href')
            for discipline in disciplines:
                if discipline in str(url):
                    if 'index.htm' in link:
                        clean_link = link.replace('index.htm','')
                    else:
                        clean_link = link
                    full_url = "http://"+clean_link+url
                    req = urllib.request.Request(full_url)

                    try:
                        res = urllib.request.urlopen(req)
                    except urllib.request.HTTPError as e:
                        print('HTTPError = ', str(e.code), full_url)
                    except urllib.request.URLError as e:
                        print('URLError = ', str(e.reason), full_url)
                    except Exception:
                        import traceback
                        print('generic exception: ', traceback.format_exc(), full_url)

                    if re.search(r'data[0-9]+', url) is not None:
                        length = 'S' if discipline[2:] == '03' else 'F'
                        seg_type = 'P' if discipline[:2] == '03' else 'D'
                        segment = length + seg_type
                        name = '_'.join([event, str(right_year), disciplines[discipline], segment])
                    else:
                        name = url
                    pdf = open(dir_path + name, 'wb')
                    pdf.write(res.read())
                    pdf.close()
                    pdf_link_list.append(full_url)
                else:
                    print('No discipline found in url: ', str(url))
    else:
        print('Top google result for ', event, year, ' returned an incorrect link')

print(pdf_link_list)

