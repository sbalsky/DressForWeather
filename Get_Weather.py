#!/usr/bin/env python
# coding: utf-8

'''
Bot to tweet clothing/gear for the weather in Seattle, daily except if clear 
and within 5 degrees of day before.

Steps: 1) Get weather from Open Weather Map API (temp, precipitation, wind);
2) Move existing "today" file to "yesterday" file & save today's high/low temps 
to file; 3) Evaluate weather criteria & set what to wear for each combination; 
4) Tweet 

To do before finished: 1) Add error checking; 2) Learn about how to test 
properly & implement enough of that to demonstrate awareness; 3) Linting

Possible future additions: 1) UV (alert if sunscreen extra needed) & atmospheric
conditions (smoke etc), 2) more finely-grained rain/snow detail, 3) Interactive! 
Tweet location to bot, get back weather for location. 4) Location-aware
'''

from requests import get
from datetime import timedelta, datetime
import yaml
import csv
import tweepy


with open("dfw_config.yml", 'r') as ymlfile:
  cfg = yaml.safe_load(ymlfile)


zone = cfg['OWM']['UTC_offset']
now = datetime.now()
dst_month = datetime(now.year, 3, 1, 2)
first_sun = timedelta(6 - dst_month.weekday())
dst_start = dst_month + first_sun + timedelta(7) #2nd Sun in March, 2 am
std_month = datetime(now.year, 11, 1, 2)
dst_end = std_month + timedelta(6 - std_month.weekday()) #1st Sun in Nov, 2 am
if now < dst_start or now >= dst_end:
    #TO DO: add if for AZ/HI, which don't observe DST
    pass
else:
    zone = zone + 1

def TimeNow(z = zone):
  dt_utc = datetime.utcnow()
  dt_loc = dt_utc + timedelta(hours=z)
  stamp = dt_loc.strftime('%D %T')
  log = dt_loc.strftime('%Y%m%d')
  t_now = datetime.replace(dt_loc,hour=0,minute=0,second=0,microsecond=0)
  tm = t_now.timestamp()
  return stamp, log, tm

now, logdate, today_midnight = TimeNow()

DAY = 24 * 60 * 60  # seconds in a day (UNIX time)
yday_date = str(round(today_midnight,0) - DAY)
logname = 'log_' + logdate + '.txt'

def WriteToLog(line, fnl=logname, m="a+"): 
  with open(fnl, m) as write_log:
    write_log.write(TimeNow()[0] + ': ')
    if type(line) == str:
      write_log.write(line +" \n")
    else:
      write_log.writelines(line)


log = "\n Run start"
WriteToLog(log)


if cfg=="":
  log = "Config file not loaded"
else:
  log = "Config file loaded"
WriteToLog(log)


# Functions to convert weather from metric (API input) to standard (US output)
# TO DO: Add checks to make sure input is in correct format +value range & needs conversion

def Kelvin_to_F(tempK):
  tempF = round(tempK*9/5 - 459.67, 0)
  return tempF

def WindConvert(meters_per_second):
  mph = 2.23694 * meters_per_second
  return mph

def WindChill(t, mps):
  if mps < 4.8 or t > 50:  # formula not defined outside these parameters
    return t
  else: 
    ws = WindConvert(mps)
    chill = 35.74 + (0.6215 * t) - (35.75 * ws^0.16) + (0.4275 * t * ws^0.16)
    return round(chill, 0)


# Step 1: Get today's forecast
def WeatherToday(): 
  # TO DO: add weather URL to config file
  # TO DO: fix config file on GitHub to keep secrets secret
  # TO DO: log these steps
  weather_url = "http://api.openweathermap.org/data/2.5/forecast?id=" + cfg['OWM']['CITY_ID'] + "&APPID=" + cfg['OWM']['APP_KEY']
    # 5 day forecast, see https://openweathermap.org/forecast5 for API documentation
  raw = get(weather_url).json()
  current = raw["list"]  
    # strips JSON header info (start at data, which is formatted as a list of dictionaries, some elements of which are also dictionaries)
    # TO DO: add checks for what if API changes format, order, etc
  today = current[0]["dt"] # first date in list, in UNIX timestamp format

  temp_mins = []
  temp_maxs = []
  winds = []
  weather_types = []
  
  for i in range(0, 4): # next 15 hours (each data point is 3h)
    temp_mins.append(current[i]["main"]["temp_min"])
    temp_maxs.append(current[i]["main"]["temp_max"])
    winds.append(current[i]["wind"]["speed"])
    
    weather = current[i]["weather"]
    w = weather[0]["main"]
    id = weather[0]["id"]  # Chart of IDs to weather type: https://openweathermap.org/weather-conditions
    if id < 300:  # categorize thunderstorms as rain
      weather_types.append("Rain")
    elif id < 700:
      weather_types.append(w)
    else:  # ignore non-precipitation types >=700
      pass  
    i+=1

  # replace real temps with windchill temps (only care how it feels)
  mins=[]
  maxs=[]
  mph=[]
  for a, b, c in zip(winds, temp_mins, temp_maxs):
    ws = WindConvert(a)
    t_min = Kelvin_to_F(b)
    t_max = Kelvin_to_F(c)
    mins.append(WindChill(t_min, ws))
    maxs.append(WindChill(t_max, ws))
    mph.append(ws)

  temp_low = min(mins)
  temp_high = max(maxs)
  wind = round(max(mph),1)

  if len(weather_types) == 0:
    precip_max = ""
  else:
    precip_max = max(weather_types)  # Drizzle < Rain < Snow; strongest conveniently in alphabetical order
    
  return {"date": today, "temp_low": temp_low, "temp_high": temp_high, "wind": wind, "type": precip_max}


# functions for string & CSV manipulation
def CombineToStr(to_display, separator=","):
  if type(to_display) is list:
    text = separator.join('{}'.format(val) for val in to_display)
  elif type(to_display) is dict:
    text = separator.join(["{} = {}".format(key, val) for key, val in to_display.items()])
  elif type(to_display) is tuple:
    text = separator.join(str(b) for b in to_display)
  else:
    text = str(to_display)
  return text

def ReadCSV(fnr):
  csv_list=[]
  value=""
  with open(fnr, mode='r') as read_file:
    f_csv = csv.reader(read_file, delimiter=',')
    for c in f_csv:
      for v in c:
        if v != ",":
          value = value + CombineToStr(v)
        else:
          csv_list.append(value)
          value=""
      csv_list.append(value) # add the last value    
  return csv_list

def WriteCSVfromList(fnw, w_list):
  w_txt = CombineToStr(w_list)
  with open(fnw, mode='w') as write_file:
    f_writer = csv.writer(write_file, delimiter=',')
    f_writer.writerow(w_txt)

    
# Step 2: Move previous day's temps to yesterday file, save today's to today file
today_file = "today.txt"
yday_file = "yesterday.txt"

def Yesterday(day):
  log = "Checking for yesterday's info from file: " + day + " \n"
  try:
    y_list = ReadCSV(today_file) # get info from existing today file (presumably now yday's info)
    date = y_list[0]
    log = log + 'Date from existing ' + today_file + ': ' + date
    if date != day: # if it isn't actually from yesterday (ie running more/less frequently)
      log = log + ' does not match expected value for yesterday. '
      try:
        y_list = ReadCSV(yday_file) # get info from existing yday file
        log = log + 'Using value from previous day instead. \n'
      except FileNotFoundError: # if there isn't an existing yday file, give it default info
        y_list = [day, cfg['Needs']['Default_low'], cfg['Needs']['Default_high']]
        log = log + 'No file found for previous day; using default values to represent yday weather. \n'
    else: # existing today list will pass through to become yday list
      log = log + 'Date matches expected; ' + today_file + ' will become ' + yday_file + '\n'
  except FileNotFoundError: # unless there isn't an existing today file
    log = log + 'No existing file found; '
    try: 
      y_list = ReadCSV(yday_file)
      log = log + 'using values from previous day instead. \n'
    except:
      y_list = [day, cfg['Needs']['Default_low'], cfg['Needs']['Default_high']]
      log = log + 'using default values for yday weather. \n'


  WriteToLog(log)
  WriteCSVfromList(yday_file, y_list)

  yday_low, yday_high = (float(y_list[i]) for i in range(1, 3))
  return {"yday_low": yday_low, "yday_high": yday_high}


wy = Yesterday(yday_date)
wt = WeatherToday()
t_list = [today_midnight, wt["temp_low"], wt["temp_high"]]
WriteCSVfromList(today_file, t_list)

  

# Step 3: Evaluate relevant conditions & report
# This can't possibly be the best way to do this but I want to move on, get the whole thing finished, then come back here
layers = [cfg['Needs']['SHORT'], cfg['Needs']['LONG'], cfg['Needs']['COAT'], cfg['Needs']['HAT'], cfg['Needs']['ALL']]
layer_desc = ["Short sleeves today! ", "Wear long sleeves. ", "You'll want a jacket. ", "Time to break out the winter coat, & remember a hat/gloves. ", "Bundle up!!! "]
layer_remove = ["No need for long sleeves today. ","Just a sweater is fine. ","You can drop down to a less puffy jacket now. ","OK with just the standard winter stuff. "]
layer_abbrev = ["T-shirt. ", "Sweater. ", "Jacket. ", "Coat/hat/gloves. ", "Bundle up! "]

yday_low = wy["yday_low"]
yday_high = wy["yday_high"]
today_low = wt["temp_low"]
today_high = wt["temp_high"]
precip = wt["type"]
wind_speed = wt["wind"]

abbrev = 0

# test replace values
# change_list = cfg['TEST']
# print((', ').join(change_list))
# yday_low = cfg['TEST']['yday_low_high']

def Short(t):
  if t >= cfg['Needs']['SHORT']:
    short = 1
  else:
    short = 0
  return short

def LayerType(t, layers):
  i = 0
  layer_type = 0
  while t <= layers[i]:
    layer_type = i
    i+=1
    if i == len(layers):
      break
  return layer_type

def InclDiff(d, y):
  diff = int(round(d - y, 0))
  noticeable = cfg['Needs']['DIFF']
  if diff >= noticeable:
    add = "Low is {} degrees warmer than yesterday. ".format(diff)
  elif diff <= -noticeable:
    add = "Low is {} degrees cooler than yesterday. ".format(-diff)
  else:
    add = ""
  return add

def Shoes(precip_type, temp):
  if precip_type == "":
    shoes = ""
    shoes_abbr = ""
  elif precip_type == "Snow" or temp <= cfg['Needs']['HAT']:
    shoes = "Warm dry boots with wool socks are in order. "
    shoes_abbr = "Warm boots. "
  elif precip_type == "Rain":
    shoes = "Waterproof boots would be a good idea. "
    shoes_abbr = "Waterproof shoes. "
  else:  # drizzle
    shoes = "Not the day for suede shoes. "
    shoes_abbr = ""

  if abbrev == 1:
    return shoes_abbr
  else:
    return shoes

def Outerwear(precip, wind, layer):
  WIND = cfg['Needs']['WIND']
  if wind >= WIND and precip == "" and layer == 0:
    outer = "Consider a light button-down: {} mph wind. ".format(round(wind_speed, 0))
    outer_abbr = "Button-down for wind. "
  elif (wind >= WIND and 1 <= layer <= 2) or (wind >= cfg['Needs']['BREEZE'] and layer == 2):
    if precip == "" or precip == "Drizzle":
      outer = "Bring a windbreaker and earband. "
      outer_abbr = "Windbreaker/earband. "
    else:
      outer = "Bring a water-resistant windbreaker and hat/umbrella. "
      outer_abbr = "Windbreaker/hat. "
  else:
    outer = 1
    outer_abbr = 1
  
  if abbrev == 1:
    return outer_abbr
  else:
    return outer

def TweetTooLong(twt):
  if len(twt) <= cfg['Twitter']['MAX_LENGTH']:
    return False
  else:
    return True

  
yday_short = Short(yday_high)
today_short = Short(today_high)

if today_short > yday_short:
  display = layer_desc[0]
else:
  display = ""

display += str(InclDiff(today_low, yday_low))
  
yday_layer = LayerType(yday_low, layers)
today_layer = LayerType(today_low, layers)

outerwear = Outerwear(precip, wind_speed, today_layer)
shoes = Shoes(precip, today_low)

if outerwear == 1:
  if today_layer > yday_layer:
    outerwear = layer_desc[today_layer]
  elif today_layer < yday_layer:
    outerwear = layer_remove[today_layer]
  else:
    outerwear = ""
else:
  pass
  
log = ["yesterday: " + str(yday_layer) + " \n", "today: " + str(today_layer) + " \n", str(outerwear) + " \n", str(shoes) + "\n"]
WriteToLog(log)


tweet_string = display + outerwear + shoes
if TweetTooLong(tweet_string):
  abbrev = 1
  shoes = Shoes(precip, today_low)
  outerwear = Outerwear(precip, wind_speed, today_layer)
  if outerwear == 1 and today_layer != yday_layer:
    outerwear = layer_abbrev[today_layer]
  else:
    outerwear = ""
  tweet_string = outerwear + shoes
else:
  pass


# Step 4: Tweet!
def TwitterPost(twt):
  twitter_auth_keys = {
    "key": cfg['Twitter']['API_KEY'],
    "secret_key": cfg['Twitter']['SECRET_KEY'],
    "token": cfg['Twitter']['TOKEN'],
    "token_secret": cfg['Twitter']['TOKEN_SECRET']
  }
 
  auth = tweepy.OAuthHandler(twitter_auth_keys['key'], twitter_auth_keys['secret_key'])
  auth.set_access_token(twitter_auth_keys['token'], twitter_auth_keys['token_secret'])
  api = tweepy.API(auth)
 
  status = api.update_status(status=twt)


#print("\nBased on today's weather: "+ CombineToStr(wt, ", "))
#print("& yday's high of {}, low of {}".format(yday_high,yday_low))
log = ["Today's weather: "+ CombineToStr(wt, ", ") + " \n", "Yesterday's high/low: " + str(yday_high) + " / " + str(yday_low) + " \n"]
WriteToLog(log)

if len(tweet_string)>0:
  #print("\nTweeted: " + tweet_string)
  log = "Tweeted: " + tweet_string
  TwitterPost(tweet_string)
else: 
  #print("\nNo tweet: Clear & similar to yesterday")
  log = "No tweet: Clear & similar to yesterday"
WriteToLog(log)

