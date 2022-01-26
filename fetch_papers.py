#!/usr/local/bin/python3

"""
Queries arxiv API and downloads papers (the query is a parameter).
The script is intended to enrich an existing database pickle (by default db.p),
so this file will be loaded first, and then new results will be added to it.
"""

import os
import time
import pickle
import random
import argparse
import urllib.request
import feedparser

from utils import Config, safe_pickle_dump, print_entry, send_email, gethtmlcat

def encode_feedparser_dict(d):
  """ 
  helper function to get rid of feedparser bs with a deep copy. 
  I hate when libs wrap simple things in their own classes.
  """
  if isinstance(d, feedparser.FeedParserDict) or isinstance(d, dict):
    j = {}
    for k in d.keys():
      j[k] = encode_feedparser_dict(d[k])
    return j
  elif isinstance(d, list):
    l = []
    for k in d:
      l.append(encode_feedparser_dict(k))
    return l
  else:
    return d

def parse_arxiv_url(url):
  """ 
  examples is http://arxiv.org/abs/1512.08756v2
  we want to extract the raw id and the version
  """
  ix = url.rfind('/')
  idversion = url[ix+1:] # extract just the id (and the version)
  parts = idversion.split('v')
  assert len(parts) == 2, 'error parsing url ' + url
  return parts[0], int(parts[1])

if __name__ == "__main__":

  # parse input arguments
  parser = argparse.ArgumentParser()
  parser.add_argument('--search-query', type=str,
                      default='cat:hep-ex+OR+hep-ph',
                      help='query used for arxiv API. See http://arxiv.org/help/api/user-manual#detailed_examples')
  parser.add_argument('--start-index', type=int, default=0, help='0 = most recent API result')
  parser.add_argument('--max-index', type=int, default=10000, help='upper bound on paper index we will fetch')
  parser.add_argument('--results-per-iteration', type=int, default=100, help='passed to arxiv API')
  parser.add_argument('--wait-time', type=float, default=5.0, help='lets be gentle to arxiv API (in number of seconds)')
  parser.add_argument('--break-on-no-added', type=int, default=1, help='break out early if all returned query papers are already in db? 1=yes, 0=no')
  parser.add_argument('--updatedTime', type=int, default=0, help='Use updated time instead of submitted time? 1=yes, 0=no')
  args = parser.parse_args()

  # misc hardcoded variables
  base_url = 'http://export.arxiv.org/api/query?' # base api query url
  print('Searching arXiv for %s' % (args.search_query, ))

  # lets load the existing database to memory
  try:
    db = pickle.load(open(Config.db_path, 'rb'))
  except Exception as e:
    print('error loading existing database:')
    print(e)
    print('starting from an empty database')
    db = {}


  filters=[
    # Topics

    ## Higgs
    'Higgs',
    'Yukawa','yukawa',
    't\bar{t}H',
    
    ## Top quark
    'Top quark', 'top quark',
    't$\bar{t}$',

    ## ttX
    'Top quark', 'top quark',
    't\bar{t}W','t\bar{t}Z','tWZ'

    ## 4 tops
    't\bar{t}t\bar{t}','4 top','four top','Four top',
    
    ## EFT
    'EFT','Effective Field Theory','effective field theory','Effective field theory',

    ## LFU
    'LFU','Lepton Flavour Universality','Lepton flavour universality','Lepton flavour universality',
    'anomaly','anomalies',

    ## MC
    'MC','Monte Carlo','Sherpa','SHERPA','MadGraph','aMC@NLO','HSF','Pythia','Herwig','powheg','Powheg','POWHEG',

    ## HF
    'heavy flavour','Heavy flavour','heavy flavor','Heavy flavor',

    
    # People

    ## MC
    'Frixione','Mattelaer','Maltoni','Frederix',
    'Siegert','Bothmann','Napoletano','Schönherr', 'Schumann',
    'Plaetzer','Preuss','Siodmok',
    'Ilten','Lonnblad','Mrenna','Skands',
    'Buckley','Gutschow','Amoroso',

    ## EFT
    'Mimasu',


  ]
    
  # Create the body of the message (a plain-text and an HTML version).
  text = ""
  html = """"""

  num_total = 0
  num_matched = 0
  num_matched_hepex = 0
  num_matched_hepph = 0
  num_matched_hepth = 0
  num_matched_other = 0


  matchedtext={"hep-ex":"""""","hep-ph":"""""","hep-th":"""""","other":""""""}
  matchedhtml={"hep-ex":"""""","hep-ph":"""""","hep-th":"""""","other":""""""}
  unmatchedtext={"hep-ex":"""""","hep-ph":"""""","hep-th":"""""","other":""""""}
  unmatchedhtml={"hep-ex":"""""","hep-ph":"""""","hep-th":"""""","other":""""""}

  htmlcat={cat:gethtmlcat(cat) for cat in matchedhtml}
  
  # -----------------------------------------------------------------------------
  # main loop where we fetch the new results
  print('database has %d entries at start' % (len(db), ))
  num_added_total = 0
  for i in range(args.start_index, args.max_index, args.results_per_iteration):

    print("Results %i - %i" % (i,i+args.results_per_iteration))
    query = 'search_query=%s&sortBy=submittedDate&start=%i&max_results=%i' % (args.search_query,
                                                                              i, args.results_per_iteration)
    if args.updatedTime: 
      query = 'search_query=%s&sortBy=lastUpdatedDate&start=%i&max_results=%i' % (args.search_query,
                                                                                  i, args.results_per_iteration)
    with urllib.request.urlopen(base_url+query) as url:
      response = url.read()
    parse = feedparser.parse(response)
    num_added = 0
    num_skipped = 0

    for e in parse.entries:

      j = encode_feedparser_dict(e)

      # extract just the raw arxiv id and version for this paper
      rawid, version = parse_arxiv_url(j['id'])
      j['_rawid'] = rawid
      j['_version'] = version

      cat=j["arxiv_primary_category"]["term"]
      if cat not in [key for key in matchedhtml]:
        cat="other"
                  
      # add to our database if we didn't have it before, or if this is a new version
      if not rawid in db or j['_version'] > db[rawid]['_version']:
        db[rawid] = j
        if not args.updatedTime: 
          print('Submitted %s added %s' % (j['published'].encode('utf-8'), j['title'].encode('utf-8')))
        else:
          print('Updated %s added %s' % (j['updated'].encode('utf-8'), j['title'].encode('utf-8')))
        num_added += 1
        num_added_total += 1
        etext,ehtml,ismatched=print_entry(args,db,rawid,filters)
        num_total+=1
        if ismatched:
          num_matched+=1
          if cat=="hep-ex":
            num_matched_hepex+=1
          elif cat=="hep-ph":
            num_matched_hepph+=1
          elif cat=="hep-th":
            num_matched_hepth+=1
          else:
            num_matched_other+=1 

            
          matchedtext[cat]=matchedtext[cat]+f"""
        {etext}
"""
          matchedhtml[cat]=matchedhtml[cat]+f"""
        {ehtml}
"""

        else:
          unmatchedtext[cat]=unmatchedtext[cat]+f"""
        {etext}
"""
          unmatchedhtml[cat]=unmatchedhtml[cat]+f"""
        {ehtml}
"""

          
      else:
        num_skipped += 1
   
    
    # print some information
    print('Added %d papers, already had %d.' % (num_added, num_skipped))

    if len(parse.entries) == 0:
      print('Received no results from arxiv. Rate limiting? Exiting. Restart later maybe.')
      print(response)
      break

    if num_added == 0 and args.break_on_no_added == 1:
      print('No new papers were added. Assuming no new papers exist. Exiting.')
      break

    print('Sleeping for %i seconds' % (args.wait_time , ))
    time.sleep(args.wait_time + random.uniform(0, 3))

  # save the database before we quit, if we found anything new
  if num_added_total > 0:
    print('Saving database with %d papers to %s' % (len(db), Config.db_path))
    safe_pickle_dump(db, Config.db_path)

  summary=f"""
Found {num_total} new entries; {num_matched} matched your filter terms:
   - hep-ex = {num_matched_hepex}
   - hep-ph = {num_matched_hepph}
   - hep-th = {num_matched_hepth}
   - other  = {num_matched_other}
"""
  subject=f"My ArXiv Update: {num_total} new, {num_matched} matched"

  text = "Josh, here is your daily arXiv update:\n"+summary+f"""
{matchedtext["hep-ex"]}
{matchedtext["hep-ph"]}
{matchedtext["hep-th"]}
{matchedtext["other"]}
------------------------------------------------------------------
{unmatchedtext["hep-ex"]}
{unmatchedtext["hep-ph"]}
{unmatchedtext["hep-th"]}
{unmatchedtext["other"]}
"""


  html = f"""
<html>
  <head></head>
  <body>
  <p>Josh, here is your daily arXiv update:</p>
  <p>"""+summary.replace('\n','<br>')+f"""</p>
  <hr>
  <h2>{htmlcat["hep-ex"]}</h2>
{matchedhtml["hep-ex"]}
  <hr>
  <h2>{htmlcat["hep-ph"]}</h2>
  {matchedhtml["hep-ph"]}
  <hr>
  <h2>{htmlcat["hep-th"]}</h2>
{matchedhtml["hep-th"]}
  <hr>
  <h2>{htmlcat["other"]}</h2>
{matchedhtml["other"]}
  <br>
  <br>
  <hr>
  <hr>
  <h1>Unmatched</h1>
  <hr>
  <h2>{htmlcat["hep-ex"]}</h2>
{unmatchedhtml["hep-ex"]}
  <hr>
  <h2>{htmlcat["hep-ph"]}</h2>
{unmatchedhtml["hep-ph"]}
  <hr>
  <h2>{htmlcat["hep-th"]}</h2>
{unmatchedhtml["hep-th"]}
  <hr>
  <h2>{htmlcat["other"]}</h2>
{unmatchedhtml["other"]}
  </body>
</html>
"""
  send_email(subject,text,html)
  print(text)
