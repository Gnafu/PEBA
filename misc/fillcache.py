#!/usr/bin/env python
# -*- coding: utf-8 -*-

# script to fill peba caches
# v0.5

import xml.etree.ElementTree as ET
import defusedxml.ElementTree as ETdefused
import hashlib
import json
import urllib.request, urllib.parse, urllib.error
import html
import datetime
from dateutil.relativedelta import relativedelta
from elasticsearch import Elasticsearch, ElasticsearchException
import pylibmc
from time import sleep
import threading

caches = []

# Make sure to match the IP to your environment !!!
es = Elasticsearch(["192.168.1.64"])


def init():
    ''' Make sure to match the memcached IPs/ports to your environment !!! '''
    for i in range(12):
        caches.append([
                    pylibmc.Client(["192.168.1.64:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["192.168.1.173:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["192.168.1.233:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["192.168.1.87:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["192.168.1.152:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["192.168.1.213:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200})

        ])

def inittest():
    ''' testing function '''
    for i in range(12):
        caches.append([
                    pylibmc.Client(["127.0.0.1:11211"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["127.0.0.1:11222"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200}),
                    pylibmc.Client(["127.0.0.1:11223"], binary=False, behaviors={"tcp_nodelay": True, "ketama": True, "connect_timeout": 200})
        ])

def testElasticsearch():
    try:
        return es.ping()
    except:
        return False

def getCache(cacheItem, cacheType):
    cacheTypeItem = cacheType + ":" + cacheItem
    rv = cache.get(cacheTypeItem)
    if rv is None:
        return False
    return rv

def testMemcached():
    for cache in caches[0]:
        try:
           cache.get("heartbeat")
        except pylibmc.Error as e:
            print("Memcache Error: {0} ".format(e))
            return False
    return True

def setCache(cacheItem, cacheValue, cacheTimeout, cacheIndex, cacheType):
    for cache in caches[cacheIndex]:
        cacheTypeItem = cacheType + ":" + cacheItem
        try:
            cache.set(cacheTypeItem, cacheValue, cacheTimeout)
        except pylibmc.Error as e:
            print("Could not set {0} to {1}".format(cacheTypeItem, e))

def checkCommunityIndex(request):
    """check if request is against community index or production index"""
    if request == 0:
        return "false"
    elif request == -1:
        return "true, false"
    return "true"

def getRelevantIndices(dayIndices):
    """calculate the relevant indices to be queried in days
        use ews-* if false
    """
    if not dayIndices:
        return "ews-*"
    else:
        allDates=""
        currentDay = "<ews-{now/d}-*>"
        allDates+=currentDay
        for i in range (1, dayIndices):
            prevDay= "<ews-{now/d-"+str(i)+"d}-*>"
            allDates+=","+prevDay
        return allDates


def queryAlertsWithoutIP(maxAlerts, clientDomain, relevantIndex):
    """ Get IP addresses from alerts in elasticsearch """

    esquery="""
    {
            "query": {
                "terms": {
                    "clientDomain": [ %s ]
                }
            },
            "sort": {
                "recievedTime": {
                    "order": "desc"
                    }
                },
            "size": %s,
            "_source": [
                "createTime",
                "peerType",
                "country",
                "originalRequestString",
                "location",
                "targetCountry",
                "countryName",
                "locationDestination",
                "recievedTime",
                "username",
                "password",
                "login",
                "clientDomain"
                ]
            }""" % (clientDomain, maxAlerts)

    try:
        res = es.search(index=relevantIndex, body=esquery)
        return res["hits"]["hits"]
    except ElasticsearchException as err:
        print('ElasticSearch error: %s' % err)

    return False

def formatAlertsJson(alertslist):
    """ Create JSON Structure for Alerts list """
    jsonarray = []

    if alertslist:

        for alert in alertslist:
            if datetime.datetime.strptime(alert['_source']['createTime'], "%Y-%m-%d %H:%M:%S") > datetime.datetime.utcnow():
                returnDate = alert['_source']['recievedTime']
                format('formatAlertsJson: createTime > now, returning recievedTime, honeypot timezone probably manually set to eastern timezone')
            else:
                returnDate = alert['_source']['recievedTime']

            latlong = alert['_source']['location'].split(' , ')
            destlatlong = alert['_source']['locationDestination'].split(' , ')

            # kippo attack details
            if alert['_source']['peerType'] == "SSH/console(cowrie)" and alert['_source']['originalRequestString'] == "":
                requestString =  ""
                if alert['_source']['username'] is not None:
                    requestString+= "Username: \"" + str(urllib.parse.unquote(alert['_source']['username'])) + "\""
                else:
                    requestString += "Username: <none>"
                if alert['_source']['password'] is not None:
                    requestString+= " | Password: \"" + str(urllib.parse.unquote(alert['_source']['password'])) + "\""
                else:
                    requestString += " | Password: <none>"
                if alert['_source']['login'] is not None:
                    requestString+= " | Status: "+ str(alert['_source']['login'])
                requestStringOut = html.escape(requestString)
            else:
                requestStringOut = html.escape(urllib.parse.unquote(alert['_source']['originalRequestString']))


            # map private IP ranges 0:0 Locations to DTAG HQ in Bonn :) # 50.708021, 7.129191
            if latlong == ["0.0","0.0"]:
                latlong = ["50.708021", "7.129191"]
                # print('formatAlertsJson: mapping location 0.0/0.0 to DTAG HQ')

            if destlatlong == ["0.0","0.0"]:
                destlatlong = ["50.708021", "7.129191"]
                # print('formatAlertsJson: mapping location 0.0/0.0 to DTAG HQ')


            jsondata = {
                'id': alert['_id'],
                'dateCreated': "%s" % returnDate,
                'country': alert['_source']['country'],
                'countryName': alert['_source']['countryName'],
                'targetCountry': alert['_source']['targetCountry'],
                'sourceLat': latlong[0],
                'sourceLng': latlong[1],
                'destLat' : destlatlong[0],
                'destLng' : destlatlong[1],
                'analyzerType': alert['_source']['peerType'],
                'requestString': '%s' % requestStringOut,
                'clientDomain': alert['_source']['clientDomain']

            }

            jsonarray.append(jsondata)
        return ({'alerts': jsonarray})

def queryTopCountriesAttacks(monthOffset, topX, clientDomain, relevantIndex):
    # use THIS month
    if monthOffset is None or monthOffset == "0" :
        span = "now/M"
        monthOffset = 0
        span2 = "now"
    # check if months is a number
    elif monthOffset.isdecimal():
        span = "now-%dM/M" % int(monthOffset)
        span2 = "now-%dM/M" % (int(monthOffset)-1)
    else:
        print('Non numeric value in topCountriesAttacks monthOffset. Must be decimal number in months')
        return False

    # use top10 default
    if topX is None:
        topx = 10
    # check if topx is a number
    elif topX.isdecimal():
        topx = topX
    else:
        print(
            'Non numeric value in topCountriesAttacks topX. Must be decimal number.')
        return False

    esquery="""{
          "query": {
            "range": {
              "recievedTime": {
                "gte": "%s",
                "lt": "%s"
              }
            }
          },
            "aggs": {
                "communityfilter": {
                    "filter": {
                        "terms": {
                            "clientDomain": [ %s ]
                        }
                    },
                    "aggs": {
            "countries": {
              "terms": {
                "field": "country.keyword",
                "size" : %s
              },
              "aggs": {
                "country": {
                  "top_hits": {
                    "size": 1,
                    "_source": {
                      "includes": [
                        "countryName"
                      ]
                    }
                  }
                }}}
              }
            }
          },
          "size": 0
        }"""% (span, span2, clientDomain, str(topx))

    # Get top 10 attacker countries
    try:
        res = es.search(index=relevantIndex, body=esquery)
    except ElasticsearchException as err:
        print('ElasticSearch error: %s' % err)

    esquery2="""{
            "query": {
                "range": {
                    "recievedTime": {
                        "gte": "%s",
                        "lt": "%s"
                    }
                }
            },
            "aggs": {
                "communityfilter": {
                    "filter": {
                        "terms": {
                            "clientDomain": [ %s ]
                        }
                    },

                    "aggs": {
                "countries": {
                    "terms": {
                        "field": "targetCountry.keyword",
                        "size" : %s
                    },
                    "aggs": {
                        "country": {
                            "top_hits": {
                                "size": 1,
                                "_source": {
                                    "includes": [
                                        "targetCountryName"
                                    ]
                                }
                            }}}
                        }
                    }
                }
            },
            "size": 0,
            "_source": [
                "createTime"
            ]
        } """ % (span, span2, clientDomain, str(topx))


    # Get top 10 attacked countries
    try:
        res2 = es.search(index=relevantIndex, body=esquery2)

        monthData = (datetime.date.today()+ relativedelta(months=-(int(monthOffset)))).strftime('%Y-%m')
        return [ res["aggregations"]["communityfilter"]["countries"]["buckets"], monthOffset, monthData, res2["aggregations"]["communityfilter"]["countries"]["buckets"] ]
    except ElasticsearchException as err:
        print('ElasticSearch error: %s' % err)

    return False

def formatTopCountriesAttacks(retrieveTopCountryAttacksArr):
        if retrieveTopCountryAttacksArr:
            retrieveTopCountryAttacker = retrieveTopCountryAttacksArr[0]
            monthOffset = retrieveTopCountryAttacksArr[1]
            monthdate = retrieveTopCountryAttacksArr[2]
            retrieveTopCountryAttacked = retrieveTopCountryAttacksArr[3]

        else:
            return ""

        # Create json structure for ATTACKER and ATTACKED countries
        jsonarray_attacker = []
        jsonarray_attacked = []

        if retrieveTopCountryAttacker and retrieveTopCountryAttacked:

            # attacker
            for topCountry in retrieveTopCountryAttacker:
                jsondata_attacker = {
                    'code': topCountry['key'],
                    'country': topCountry['country']['hits']['hits'][0]['_source']['countryName'],
                    'count': topCountry['doc_count']
                }
                jsonarray_attacker.append(jsondata_attacker)

            # attacked
            for topCountry in retrieveTopCountryAttacked:
                jsondata_attacked = {
                    'code': topCountry['key'],
                    'country': topCountry['country']['hits']['hits'][0]['_source']['targetCountryName'],
                    'count': topCountry['doc_count']
                }
                jsonarray_attacked.append(jsondata_attacked)

        countryStats = {'id': monthOffset,
                        'date': monthdate,
                        'attacksPerCountry': jsonarray_attacker,
                        'attacksToTargetCountry': jsonarray_attacked
                        }
        return ([countryStats])

def queryAlertStats(clientDomain,relevantIndex):
    """ Get combined statistics from elasticsearch """
    esquery = """{
               "aggs": {
                   "communityfilter": {
                       "filter": {
                           "terms": {
                               "clientDomain": [ %s ]
                           }
                       },
               "aggs": {
               "ctr": {
                 "range": {
                   "field": "recievedTime",
                   "ranges": [
                     {
                       "key": "1d",
                       "from": "now-1440m"
                     },
                     {
                       "key": "1h",
                       "from": "now-60m"
                     },
                     {
                       "key": "5m",
                       "from": "now-5m"
                     },
                     {
                       "key": "1m",
                       "from": "now-1m"
                     }
                   ]
                 }
               }}}
             },
             "size": 0
           }""" % clientDomain

    try:
        res = es.search(index=relevantIndex, body=esquery)
        return res['aggregations']['communityfilter']['ctr']['buckets']
    except ElasticsearchException as err:
        print('ElasticSearch error: %s' % err)

    return False

def formatAlertStats(retrieveAlertStat):
    if retrieveAlertStat:
        jsondata = {
            'AlertsLast24Hours': retrieveAlertStat[0]['doc_count'],
            'AlertsLastHour': retrieveAlertStat[1]['doc_count'],
            'AlertsLast5Minutes': retrieveAlertStat[2]['doc_count'],
            'AlertsLastMinute': retrieveAlertStat[3]['doc_count']
        }
        return (jsondata)
    else:
        return ""

def queryAlertsCountWithType(timeframe, clientDomain, relevantIndex):
    """ Get number of Alerts in timeframe in elasticsearch """

    # check if timespan = d or number
    if timeframe == "day":
        span = "now/d"
    elif timeframe.isdecimal():
        span = "now-%sm" % timeframe
    else:
        print('Non numeric value in retrieveAlertsCountWithType timespan. Must be decimal number (in minutes) or string "day"')
        return False

    esquery=""" 
    {
          "query": {
            "range": {
              "recievedTime": {
                  "gte": "%s"
              }
            }
          },
          "aggs": {
            "communityfilter": {
              "filter": {
                "terms": {
                  "clientDomain": [ %s ] 
                }
              },
              "aggs": {
                "honeypotTypes": {
                  "terms": {
                    "field": "peerType.keyword"
                  }
                }
              }
            }
          },
          "size": 0
        }
    """ % (span, clientDomain)

    try:
        res = es.search(index=relevantIndex, body=esquery)
        return res
    except ElasticsearchException as err:
        print('ElasticSearch error: %s' %  err)

    return False

def formatAlertsCountWithType(numberofalerts):
    if numberofalerts:
        jsondata1 = {}
        for alertTypes in numberofalerts['aggregations']['communityfilter']['honeypotTypes']['buckets']:
            jsondata1[alertTypes['key']] = alertTypes['doc_count']

        jsondata2 = {
            "AlertCountTotal": numberofalerts['aggregations']['communityfilter']['doc_count'],
            "AlertCountPerType": jsondata1
        }
        return (jsondata2)
    else:
        return ""


########################
### string variables
########################
# variables for sicherheitstacho.eu requests

domain = "https://community.sicherheitstacho.eu"
itemRetrieveAlertsJsonCommunity="/alert/retrieveAlertsJson?ci=1&topx=35"
itemRetrieveAlertsJson="/alert/retrieveAlertsJson?ci=0&topx=35"
itemRetrieveAlertsJsonAll="/alert/retrieveAlertsJson?ci=-1&topx=35"
itemTopCountriesAttacksCommunity="/alert/topCountriesAttacks?ci=1"
itemTopCountriesAttacks="/alert/topCountriesAttacks?ci=0"
itemTopCountriesAttacksAll="/alert/topCountriesAttacks?ci=-1"
itemRetrieveAlertStatsCommunity="/alert/retrieveAlertStats?ci=1"
itemRetrieveAlertStats="/alert/retrieveAlertStats?ci=0"
itemRetrieveAlertStatsAll="/alert/retrieveAlertStats?ci=-1"
itemAlertsCountWithTypeCommunity="/alert/retrieveAlertsCountWithType?time=1&ci=1"
itemAlertsCountWithType="/alert/retrieveAlertsCountWithType?time=1&ci=0"
itemAlertsCountWithTypeAll="/alert/retrieveAlertsCountWithType?time=1&ci=-1"


########################
### Thread Functions
#######################

# routes
## /retrieveAlertsJson
def fillCacheRetrieveAlertsJson(sleeptime, cachetime, community):
    while True:
        numAlerts = 35
        returnResult = formatAlertsJson(queryAlertsWithoutIP(numAlerts, checkCommunityIndex(community), getRelevantIndices(2)))
        if community == 0:
            cacheItem=domain+itemRetrieveAlertsJson
            cacheIndex=0
        elif community == 1:
            cacheItem=domain+itemRetrieveAlertsJsonCommunity
            cacheIndex = 1
        elif community == -1:
            cacheItem=domain+itemRetrieveAlertsJsonAll
            cacheIndex=8
        settingResult=setCache(cacheItem, returnResult, cachetime, cacheIndex, "url")
        sleep(sleeptime)

## /topCountriesAttacks
def fillCacheTopCountriesAttacks(sleeptime, cachetime, community):
    while True:
        returnResult = formatTopCountriesAttacks(queryTopCountriesAttacks(None, None, checkCommunityIndex(community), getRelevantIndices(0)))
        if community == 0:
            cacheItem=domain+itemTopCountriesAttacks
            cacheIndex = 2
        elif community == 1:
            cacheItem=domain+itemTopCountriesAttacksCommunity
            cacheIndex = 3
        elif community == -1:
            cacheItem=domain+itemTopCountriesAttacksAll
            cacheIndex = 9
        settingResult=setCache(cacheItem, returnResult, cachetime, cacheIndex, "url")
        sleep(sleeptime)


## /retrieveAlertStats
def fillRetrieveAlertStats(sleeptime, cachetime, community):
    while True:
        returnResult = formatAlertStats(queryAlertStats(checkCommunityIndex(community), getRelevantIndices(2)))
        if community == 0:
            cacheItem=domain+itemRetrieveAlertStats
            cacheIndex = 4
        elif community == 1:
            cacheItem=domain+itemRetrieveAlertStatsCommunity
            cacheIndex = 5
        elif community == -1:
            cacheItem=domain+itemRetrieveAlertStatsAll
            cacheIndex = 10
        settingResult=setCache(cacheItem, returnResult, cachetime, cacheIndex, "url")
        sleep(sleeptime)

## /retrieveAlertsCountWithType
def fillRetrieveAlertsCountWithType(sleeptime, cachetime, community):
    while True:
        returnResult = formatAlertsCountWithType(queryAlertsCountWithType("1", checkCommunityIndex(community), getRelevantIndices(2)))
        if community == 0:
            cacheItem = domain + itemAlertsCountWithType
            cacheIndex = 6
        elif community == 1:
            cacheItem = domain + itemAlertsCountWithTypeCommunity
            cacheIndex = 7
        elif community == -1:
            cacheItem = domain + itemAlertsCountWithTypeAll
            cacheIndex = 11
        settingResult=setCache(cacheItem, returnResult, cachetime, cacheIndex, "url")
        sleep(sleeptime)


########################
### Start Cache filling
#######################

if __name__ == '__main__':

    init()

    # for local testing

    #inittest()

    print("******** FILLING PEBA CACHE **********")


    if not testElasticsearch():
        print("Elasticsearch is not accessible")
        exit(1)
    if not testMemcached():
        print("No all configured Memcached are accessible")
        exit(1)


    ## /retrieveAlertsJson
    tRetrieveAlertsJsonCommunity = threading.Thread(target=fillCacheRetrieveAlertsJson, args=(10,60,1,))
    tRetrieveAlertsJsonCommunity.start()
    tRetrieveAlertsJson = threading.Thread(target=fillCacheRetrieveAlertsJson, args=(10,60,0,))
    tRetrieveAlertsJson.start()
    tRetrieveAlertsJsonAll = threading.Thread(target=fillCacheRetrieveAlertsJson, args=(10,60,-1,))
    tRetrieveAlertsJsonAll.start()

    ## /topCountriesAttacks
    tTopCountriesAttacksCommunity = threading.Thread(target=fillCacheTopCountriesAttacks, args=(10,60,1,))
    tTopCountriesAttacksCommunity.start()
    tTopCountriesAttacks = threading.Thread(target=fillCacheTopCountriesAttacks, args=(10,60,0,))
    tTopCountriesAttacks.start()
    tTopCountriesAttacksAll = threading.Thread(target=fillCacheTopCountriesAttacks, args=(10, 60, -1,))
    tTopCountriesAttacksAll.start()

    ## /retrieveAlertStats
    tRetrieveAlertStatsCommunity = threading.Thread(target=fillRetrieveAlertStats, args=(10,60,1,))
    tRetrieveAlertStatsCommunity.start()
    tRetrieveAlertStats = threading.Thread(target=fillRetrieveAlertStats, args=(10,60,0,))
    tRetrieveAlertStats.start()
    tRetrieveAlertStatsAll = threading.Thread(target=fillRetrieveAlertStats, args=(10,60,-1,))
    tRetrieveAlertStatsAll.start()


    ## /retrieveAlertsCountWithType
    tRetrieveAlertsCountWithTypeCommunity = threading.Thread(target=fillRetrieveAlertsCountWithType, args=(10,60,1,))
    tRetrieveAlertsCountWithTypeCommunity.start()
    tRetrieveAlertsCountWithType = threading.Thread(target=fillRetrieveAlertsCountWithType, args=(10,60,0,))
    tRetrieveAlertsCountWithType.start()
    tRetrieveAlertsCountWithTypeAll = threading.Thread(target=fillRetrieveAlertsCountWithType, args=(10,60,-1,))
    tRetrieveAlertsCountWithTypeAll.start()


    print(str(threading.active_count()) + " Threads started. Filling cache...")