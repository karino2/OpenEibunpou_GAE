import webapp2
import csv
import json
from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import users
from datetime import time
from datetime import datetime

def getTickCount():
    return int((datetime.now()-datetime(2010, 1, 1)).total_seconds())

class Question(ndb.Model):
	year = ndb.StringProperty()
	questionNumber = ndb.IntegerProperty()
	subQuestionNumber = ndb.StringProperty()
	questionBody = ndb.StringProperty()
	options = ndb.StringProperty()
	answer = ndb.StringProperty() # might be list, so I use String
	questionType = ndb.IntegerProperty()


class CompletionQuestion(ndb.Model):
	userId = ndb.StringProperty() #email address
	year = ndb.StringProperty()
	subQuestionNumber = ndb.StringProperty()
	completion = ndb.IntegerProperty() #0-100
	date = ndb.IntegerProperty() #use time value for interop

class CompletionStage(ndb.Model):
	userId = ndb.StringProperty() #email address
	year = ndb.StringProperty()
	completion = ndb.IntegerProperty() #0-100
	date = ndb.IntegerProperty()

def buildJsonFromCompletionQuestionsForSpecificYear(completions):
	res = []
	for q in completions:
		obj = { 'sub': q.subQuestionNumber,
			'comp': q.completion,
			'date' : q.date
			}
		res.append(obj)
	return res

def buildJsonFromCompletionQuestions(tick, completions):
	lis = []
	for q in completions:
		obj = { 'year': q.year,
			'sub': q.subQuestionNumber,
			'comp': q.completion,
			'date' : q.date
			}
		lis.append(obj)
	return { 'date': tick,  'comps': lis }


# http://localhost:8080/compyear/24-1/1234876
class StageQuestionCompletionHandler(webapp2.RequestHandler):
	def get(self, year, fromTickS):
            fromTick = int(fromTickS)
            user = users.get_current_user()
            if not user:
                self.redirect(users.create_login_url(self.request.uri))
                return
            compList = CompletionQuestion.query(ndb.AND(CompletionQuestion.userId == user.email(), ndb.AND(CompletionQuestion.year == year, CompletionQuestion.date > fromTick))).fetch(100)
            self.response.headers['Content-Type'] = 'application/json'
            self.response.write(json.dumps(buildJsonFromCompletionQuestionsForSpecificYear(compList)))

# return lowest 100 completion.
# http://localhost:8080/complow/1234876
# return value is { 'date': 1234567, 'comps': [{'year': '23-1', 'sub': 'A-1', 'comp': 30, 'date': 12321}, ...] }
class LowestQuestionCompletionHandler(webapp2.RequestHandler):
	def get(self, fromTickS):
            fromTick = int(fromTickS)
            user = users.get_current_user()
            if not user:
                self.redirect(users.create_login_url(self.request.uri))
                return
            tick = getTickCount()
            #compList = CompletionQuestion.query(ndb.AND(CompletionQuestion.userId == user.email(), CompletionQuestion.date > fromTick)).order(CompletionQuestion.completion).fetch(100)
            compList = CompletionQuestion.query(CompletionQuestion.userId == user.email()).order(CompletionQuestion.completion).fetch(100)
            compList = [x for x in compList if x.date > fromTick]
            self.response.headers['Content-Type'] = 'application/json'
            self.response.write(json.dumps(buildJsonFromCompletionQuestions(tick, compList)))

# /cqupdate 'json': {"stagen": "27-1", "stagec": 78, "comps": [{sub:'A-3', comp: 100},...]}"
class CompletionUpdateHandler(webapp2.RequestHandler):
	def post(self):
		user = users.get_current_user()
		if not user:
			self.redirect(users.create_login_url(self.request.uri))
			return
		obj = json.loads(self.request.get('json'))
                year = obj['stagen']
                stageComp = obj['stagec']
		ents = obj['comps']
                stored = CompletionQuestion.query(ndb.AND(CompletionQuestion.userId == user.email(), CompletionQuestion.year == year)).fetch(100)
                sdict = {}
                for c in stored:
                    sdict[c.subQuestionNumber] = c
                tick = getTickCount()
                pendings = []
                rests = []
		for ent in ents:
                    if sdict.has_key(ent['sub']):
                        c = sdict[ent['sub']]
                        c.completion = ent['comp']
                        c.date = tick
                        pendings.append(c)
                    else:
                        comp = CompletionQuestion(
                            userId = user.email(),
                            year = year,
                            subQuestionNumber = ent['sub'],
                            completion = int(ent['comp']),
                            date = tick
                            )
                        pendings.append(comp)
		ndb.put_multi(pendings)
		self.response.headers['Content-Type'] = 'text/plain'
		self.response.write(tick)


def getYears():
	years = memcache.get('years')
	if years is not None:
		return years
	else:
		yearsList = Question.query(projection=[Question.year], distinct=True).fetch(100)
		years = []
		for ent in yearsList:
			years.append(ent.year)
		memcache.set('years', years)
		return years
		
	

class MainPage(webapp2.RequestHandler):
	def get(self):
		user = users.get_current_user()
		if not user:
			self.redirect(users.create_login_url(self.request.uri))
			return
                self.response.out.write("""
                    <html>
            <body>
              <form action="/cqupdate/27-1" method="post">
                <div><textarea name="json" rows="3" cols="60"></textarea></div>
                <div><input type="submit" value="post"></div>
              </form>
            </body>s
          </html>""")


def buildJsonFromQuestions(questions):
	res =[]
	for q in questions:
		obj = { 'sub': q.subQuestionNumber,
			'body': q.questionBody,
			'options': json.loads('[' + q.options +']'),
			'answer' : json.loads('[' + q.answer +']'),
			'type': q.questionType }
		res.append(obj)
	return res

# http://localhost:8080/questions/24-1
class QuestionsHandler(webapp2.RequestHandler):
	def get(self, year):
		user = users.get_current_user()
		if user:
			q = Question.query(Question.year==year).fetch(100)
			# self.response.headers['Content-Type'] = 'text/plain'
			jsonRes = buildJsonFromQuestions(q)
			self.response.headers['Content-Type'] = 'application/json'
			self.response.write(json.dumps(jsonRes))
		else:
			self.redirect(users.create_login_url(self.request.uri))



class YearsHandler(webapp2.RequestHandler):
	def get(self):
		user = users.get_current_user()
		if not user:
			self.redirect(users.create_login_url(self.request.uri))
			return
		years = getYears()
		self.response.headers['Content-Type'] = 'application/json'
		self.response.write(json.dumps(years))
		

class SaveToLocalPage(webapp2.RequestHandler):
	def get(self):
		if not users.is_current_user_admin():
			self.redirect(users.create_login_url(self.request.uri))
			return
		with open('grammer_data.csv', 'r') as csvfile:
			reader =csv.reader(csvfile)
			firstLine = True
			entities = []
			for row in reader:
				if firstLine:
					firstLine = False
					continue
				question = Question(year = row[0],
					questionNumber = int(row[1]),
					subQuestionNumber = row[2],
					questionBody = row[3],
					options = row[4],
					answer = row[5],
					questionType = int(row[6]))
				entities.append(question)
		ndb.put_multi(entities)
		self.response.headers['Content-Type'] = 'text/plain'
		self.response.write('Written!')

app = webapp2.WSGIApplication([
	('/', MainPage),
	(r'/questions/(.*)', QuestionsHandler),
	(r'/compyear/(.*)/(.*)', StageQuestionCompletionHandler),
	('/cqupdate', CompletionUpdateHandler),
	(r'/complow/(.*)', LowestQuestionCompletionHandler),
	('/save', SaveToLocalPage),
	('/years', YearsHandler),
], debug=True)
