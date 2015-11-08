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

class UserPost(ndb.Model):
    owner = ndb.StringProperty() #email
    year = ndb.StringProperty()
    subQuestionNumber = ndb.StringProperty()
    anonymous = ndb.IntegerProperty() #0 or 1
    parent = ndb.IntegerProperty()
    childrenNum = ndb.IntegerProperty()
    like = ndb.IntegerProperty()
    dislike = ndb.IntegerProperty()
    report = ndb.IntegerProperty()
    body = ndb.StringProperty()
    date = ndb.IntegerProperty() #posted tick

class LikeDislike(ndb.Model):
    postId = ndb.IntegerProperty()
    year = ndb.StringProperty()
    subQuestionNumber = ndb.StringProperty()
    user = ndb.StringProperty() #email
    val = ndb.IntegerProperty() #-1,0,1
    date = ndb.IntegerProperty()

# /likes/27-1/12345432
class LikeDislikeListHandler(webapp2.RequestHandler):
    def get(self, year, fromTickS):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        fromTick = int(fromTickS)
        likes = LikeDislike.query(ndb.AND(LikeDislike.user == user.email(), ndb.AND(LikeDislike.year == year, LikeDislike.date > fromTick)))
        objs = map((lambda like: {"postId": like.postId, "val": like.val, "date": like.date} ), likes)
        self.response.headers['Content-Type'] = 'application/json'
        self.response.write(json.dumps(objs))

# /like json: {"id": 1234567, "val": 1}
class LikeDislikeHandler(webapp2.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        obj = json.loads(self.request.get('json'))
        tick = getTickCount()
        post = UserPost.get_by_id(obj['id'])
        if post == None:
            self.response.set_status(400)
            self.response.write('Bad request. Specified post not found.')
            return
        likeDislikes = LikeDislike.query(ndb.AND(LikeDislike.postId == obj['id'], LikeDislike.user == user.email())).fetch(1)
        newVal = obj['val']
        deltaLike = 0
        deltaDislike = 0
        if len(likeDislikes) == 1:
            like = likeDislikes[0]
            if like.val == newVal:
                # do nothing
                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write("do nothing.")
                return
            oldVal = like.val
            if oldVal == 1:
                deltaLike = -1
            elif oldVal == -1:
                deltaDislike = -1
            like.val = newVal
            like.date = tick
            like.put()
        else:
            like = LikeDislike(    
                postId = obj['id'],
                year = post.year,
                subQuestionNumber = post.subQuestionNumber,
                user = user.email(),
                date = tick,
                val = newVal)
            like.put()
            delta = newVal
        if newVal == 1:
            deltaLike += 1
        elif newVal == -1:
            deltaDislike += 1
        # post.like and post.dislike is not exact number but just cache, so take care for illegal case.
        post.like = max(0, post.like+deltaLike)
        post.dislike = max(0, post.dislike+deltaDislike)
        post.date = tick
        post.put()
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(tick)

def buildJsonFromPostList(posts, userid):
    res = []
    for p in posts:
        owner = p.owner
        if p.anonymous and p.owner != userid:
            owner = ""
        obj = {
            'id': p.key.id(),
            'owner': owner,
            'anonymous': p.anonymous,
            'year': p.year,
            'sub': p.subQuestionNumber,
            'parent': p.parent,
            'body': p.body,
            'like': p.like,
            'dislike': p.dislike,
            'date': p.date
            }
        res.append(obj)
    return res;

class UserPostListBase(webapp2.RequestHandler):
    def query(self):
        pass
    def baseGet(self, fromTickS):
        fromTick = int(fromTickS)
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        self.fromTick = fromTick
        self.user = user
        posts = self.query()
        self.response.headers['Content-Type'] = 'application/json'
        self.response.write(json.dumps(buildJsonFromPostList(posts, user.email())))

# http://localhost:8080/posts/24-1/1234876
class UserPostListHandler(UserPostListBase):
    def query(self):
        return UserPost.query(ndb.AND(UserPost.year == self.year, UserPost.date > self.fromTick))
    def get(self, year, fromTickS):
        self.year = year
        self.baseGet(fromTickS)

# return latest 20
# http://localhost:8080/nposts/1234876
class UserPostLatestListHandler(UserPostListBase):
    def query(self):
        return UserPost.query(UserPost.date > self.fromTick).order(-UserPost.date).fetch(20)
    def get(self, fromTickS):
        self.baseGet(fromTickS)

# cmd: 0 update, 1 delete
# /pupdate json: {"id": 1234567, "cmd": 0, "anon": 0, "body": "hogehoge ikaika"}
class UserPostUpdateHandler(webapp2.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        obj = json.loads(self.request.get('json'))
        post = UserPost.get_by_id(obj['id'])
        if post == None:
            self.response.set_status(400)
            self.response.write('Bad request. Specified post not found.')
            return
        if post.owner != user.email():
            self.response.set_status(403)
            self.response.write('Not a owner')
            return
        tick = getTickCount()
        if obj['cmd'] == 1:
            post.key.delete()
        else:
            post.anonymous = int(obj['anon'])
            post.body = obj['body']
            post.date = tick
            post.put()
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(tick)

            

# /post json: {"year": "27-1", "sub": "A-3", "anon": 0, "body": "hogehoge ikaika"}
class UserPostHandler(webapp2.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return
        tick = getTickCount()
        obj = json.loads(self.request.get('json'))
        post = UserPost(
            owner = user.email(),
            year = obj['year'],
            subQuestionNumber = obj['sub'],
            anonymous = int(obj['anon']),
            parent = 0,
            like = 0,
            dislike = 0,
            report = 0,
            body = obj['body'],
            date = tick)
        id = post.put()
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(id)



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
              UserPost post.
              <form action="/like" method="post">
                <div><textarea name="json" rows="3" cols="60"></textarea></div>
                <div><input type="submit" value="post"></div>
              </form>
            </body>
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
	(r'/posts/(.*)/(.*)', UserPostListHandler),
	(r'/nposts/(.*)', UserPostLatestListHandler),
	('/pupdate', UserPostUpdateHandler),
	('/post', UserPostHandler),
	(r'/likes/(.*)/(.*)', LikeDislikeListHandler),
	('/like', LikeDislikeHandler),
	('/save', SaveToLocalPage),
	('/years', YearsHandler),
], debug=True)
