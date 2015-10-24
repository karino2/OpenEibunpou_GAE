import webapp2
import csv
import json
from google.appengine.ext import ndb
from google.appengine.api import memcache

class Question(ndb.Model):
	year = ndb.StringProperty()
	questionNumber = ndb.IntegerProperty()
	subQuestionNumber = ndb.StringProperty()
	questionBody = ndb.StringProperty()
	options = ndb.StringProperty()
	answer = ndb.StringProperty() # might be list, so I use String
	questionType = ndb.IntegerProperty()
	
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
		q = Question.query().fetch(1)[0]
		self.response.headers['Content-Type'] = 'text/plain'
		self.response.write(q.key.id())
		
		
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
		q = Question.query(Question.year==year).fetch(100)
		# self.response.headers['Content-Type'] = 'text/plain'
		jsonRes = buildJsonFromQuestions(q)
		self.response.headers['Content-Type'] = 'application/json'
		self.response.write(json.dumps(jsonRes))


class YearsHandler(webapp2.RequestHandler):
	def get(self):
		years = getYears()
		self.response.headers['Content-Type'] = 'application/json'
		self.response.write(json.dumps(years))
		

class SaveToLocalPage(webapp2.RequestHandler):
	def get(self):
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
	('/save', SaveToLocalPage),
	('/years', YearsHandler),
], debug=True)
