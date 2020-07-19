from flask import Flask, request, jsonify
import requests, re, json, os
from threading import Event, Thread

app = Flask(__name__)
app.url_map.strict_slashes = False

todayData = {}
totalData = {}
jsonToday = {}
jsonTotal = {}
jsonAll = {}
jsonDataset = {}
sourceCode = ''
sourceCleaned = ''
lastUpdated = ''
telegramAPI_Token = os.getenv('TELEGRAM_API_TOKEN', '')
telegramChatID = os.getenv('TELEGRAM_CHAT_ID', '')
checkInterval = 300 # seconds

monthsTRtoEN = {'OCAK': 'JANUARY', 'ŞUBAT': 'FEBRUARY', 'MART': 'MARCH',
				'NİSAN': 'APRIL', 'MAYIS': 'MAY', 'HAZİRAN': 'JUNE',
				'TEMMUZ': 'JULY', 'AĞUSTOS': 'AUGUST', 'EYLÜL': 'SEPTEMBER',
				'EKİM': 'OCTOBER', 'KASIM': 'NOVEMBER', 'ARALIK': 'DECEMBER'}
monthsTRtoIndex = {'OCAK': '01', 'ŞUBAT': '02', 'MART': '03',
					'NİSAN': '04', 'MAYIS': '05', 'HAZİRAN': '06',
					'TEMMUZ': '07', 'AĞUSTOS': '08', 'EYLÜL': '09',
					'EKİM': '10', 'KASIM': '11', 'ARALIK': '12'}
# newLine = '%0A'

replaceTR_HTML = (lambda x: x.replace('&#x11E;', 'Ğ').replace('&#x130;', 'İ').replace('&#x15E;', 'Ş'))
replaceTRUpper = (lambda x: x
				.replace('Ç', 'C').replace('İ', 'I').replace('Ğ', 'G')
				.replace('Ö', 'O').replace('Ş', 'S').replace('Ü', 'U'))


class TimerThread(Thread):
	def __init__(self, event):
		Thread.__init__(self)
		self.stopped = event

	def run(self):
		while not self.stopped.wait(checkInterval):
			getData()


def dateTRtoEN(date):
	month = re.findall('\s.*?\s', date)[0].strip()
	dateEN = re.sub(month, monthsTRtoEN[month], date)

	return dateEN


def getLastUpdate():
	global lastUpdated

	lastUpdateStr = re.findall('<div\sclass="takvim text-center ">.*?</div>', sourceCleaned)[0]
	lastUpdateStr = re.sub('<div.*?>|</div>', '', lastUpdateStr)
	lastUpdateStr = replaceTR_HTML(lastUpdateStr)
	lastUpdateList = re.findall('<p.*?</p>', lastUpdateStr)
	lastUpdateList = [re.sub('<p.*?>|</p>', '', p) for p in lastUpdateList]

	lastUpdateList[0] = '0' + lastUpdateList[0] if len(lastUpdateList[0]) == 1 else lastUpdateList[0]
	lastUpdated = lastUpdateList[2] + '-' + monthsTRtoIndex[lastUpdateList[1]] + '-' + lastUpdateList[0]


def getDate(key):
	dateStr = re.findall('{}:\s\[.*?]'.format(key), sourceCleaned)[0]
	dateStr = dateStr.replace('{}: '.format(key), '')

	return json.loads(dateStr)


def getDataset(key, datasetsStr):
	dataStr = re.findall('id:\s\"{}.*?\]'.format(key), datasetsStr)[0]
	dataStr = re.sub('id.*?data:\s', '', dataStr)

	return json.loads(dataStr)


def prepareDataset():
	global jsonDataset

	dates = getDate('labelsTooltip')
	dateLabels = getDate('labels')

	datasets = re.findall('datasets:\s\[.*?\}\]', sourceCleaned)[0]
	cases = getDataset('vaka', datasets)
	deaths = getDataset('vefat', datasets)

	datesEN = []
	for date in dates:
		datesEN.append(dateTRtoEN(date))

	jsonDataset = {'dates': datesEN, 'dateLabels': dateLabels, 'cases': cases, 'deaths': deaths}


def createJSONs():
	global jsonToday, jsonTotal, jsonAll

	totalLabelsTRtoEN = {'TOPLAM TEST SAYISI': 'test',
						'TOPLAM VAKA SAYISI': 'case',
						'TOPLAM VEFAT SAYISI': 'death',
						'TOPLAM YOĞUN BAKIM HASTA SAYISI': 'icuPatient',
						'TOPLAM ENTUBE HASTA SAYISI': 'intubatedPatient',
						'TOPLAM İYİLEŞEN HASTA SAYISI': 'recoveredPatient'}
	todayLabelsTRtoEN = {'BUGÜNKÜ TEST SAYISI': 'test',
						'BUGÜNKÜ VAKA SAYISI': 'case',
						'BUGÜNKÜ VEFAT SAYISI': 'death',
						'BUGÜNKÜ İYİLEŞEN SAYISI': 'recoveredPatient'}

	for key, value in todayData.items():
		jsonToday[todayLabelsTRtoEN[key]] = value
	for key, value in totalData.items():
		jsonTotal[totalLabelsTRtoEN[key]] = value
	jsonAll = {'today': jsonToday, 'total': jsonTotal}


def prepareData():
	global todayData, totalData, sourceCode, sourceCleaned

	unorderedLists = re.findall('<ul.*?</ul>', sourceCleaned)[:-1]
	for uList in unorderedLists:
		spans = re.findall('<span.*?</span>', uList)
		it = iter(spans)
		spans = list(zip(it, it))

		for span in spans:
			key = re.sub('<s.*?>|<\/s.*?>', '', span[0]).replace('<br>', ' ')
			value = re.sub('<s.*?>|<\/s.*?>', '', span[1]).replace('<br>', ' ')
			if key.startswith('TOP'):
				totalData[key] = value
			else:
				todayData[key] = value
			print(key, ':', value)


def getData():
	global todayData, sourceCode, sourceCleaned, jsonToday

	try:
		r = requests.get('https://covid19.saglik.gov.tr')
		if r.text == sourceCode:
			return
		sourceCode = r.text
		sourceCleaned = r.text.replace('  ', '').replace('\r\n', '')
		sourceCleaned = re.sub('<!--.*?-->', '', sourceCleaned)

		getLastUpdate()
		prepareData()
		sendTelegram()
		createJSONs()
		prepareDataset()
	except Exception as e:
		print('>>>[ERROR] Cannot get data!', e)
		return


def sendTelegram():
	text = 'Son güncellenme tarihi: *{}*\n'.format(lastUpdated)
	for key, value in todayData.items():
		text += '_' + key + ':_  '
		text += '*' + value + '*'
		text += '\n'
	text += '\n'
	for key, value in totalData.items():
		text += '_' + key + ':_  '
		text += '*' + value + '*'
		text += '\n'
	text = text.replace('.', '\\.').replace('-', '\\-')

	headers = {'Content-Type': 'application/json'}
	payload = {'chat_id': telegramChatID, 'parse_mode': 'MarkdownV2', "text": text}

	telegramURL = 'https://api.telegram.org/' + telegramAPI_Token + '/sendMessage'
	print(telegramURL)
	print(payload)
	try:
		r = requests.post(telegramURL, headers=headers, data=json.dumps(payload))
		print(r.status_code)
	except Exception as e:
		print('>>>[ERROR] Cannot send message !', e)


@app.route('/today', methods=['GET'])
def getToday():
	if jsonToday != {}:
		responseData = dict(jsonToday)
		responseData['lastUpdated'] = lastUpdated
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


@app.route('/total', methods=['GET'])
def getTotal():
	if jsonTotal != {}:
		responseData = dict(jsonTotal)
		responseData['lastUpdated'] = lastUpdated
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


@app.route('/all', methods=['GET'])
def getAll():
	if jsonAll != {}:
		responseData = dict(jsonAll)
		responseData['lastUpdated'] = lastUpdated
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


@app.route('/datasets/all', methods=['GET'])
def getAllDataset():
	if jsonDataset != {}:
		responseData = dict(jsonDataset)
		responseData['lastUpdated'] = lastUpdated
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


@app.route('/datasets/cases', methods=['GET'])
def getCasesDataset():
	if jsonDataset != {}:
		responseData = {'dates': jsonDataset['dates'],
						'dateLabels': jsonDataset['dateLabels'],
						'cases': jsonDataset['cases'],
						'lastUpdated': lastUpdated}
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


@app.route('/datasets/deaths', methods=['GET'])
def getDeathsDataset():
	if jsonDataset != {}:
		responseData = {'dates': jsonDataset['dates'],
						'dateLabels': jsonDataset['dateLabels'],
						'deaths': jsonDataset['deaths'],
						'lastUpdated': lastUpdated}
		return(jsonify(responseData), 200)
	else:
		return ('', 404)


if __name__ == '__main__':
	getData()
	stopFlag = Event()
	thread = TimerThread(stopFlag)
	thread.start()
	app.run(debug=False, port=5000, host= '0.0.0.0')
