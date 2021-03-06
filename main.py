# Copyright (c) 2013 by LIANG FANG 
# New York University, Courant Institute, Dept. of Computer Science

import os
import urllib

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.ext import db

import webapp2
import jinja2
import re
import string
import datetime

### Jinja2 Environment Variable ###

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


### Model Class and helper functions ###

class Post(db.Model):           
    """ This is Post Model  """
    title = db.StringProperty()
    content = db.TextProperty(default = "")
    created_time = db.DateTimeProperty(auto_now_add=True)   
    modify_time = db.DateTimeProperty(auto_now=True)  # change to current time automatically when post modified
    tags = db.ListProperty(db.Key)                    # store keys of this post's tags
    def tagList(self):                  # return list of tag entities of this post(used in singleblog.html under Jinja2)
        return [Tag.get(key) for key in self.tags]
    def tagStr(self):                   # return string of tags, separated by comma
        return " ".join([Tag.get(x).tag for x in self.tags])
    def contentFormat(self):            # process post content so that http link and pictures can be displayed
        return content_filter(self.content)
    def modifytimeinEST(self):
        return self.modify_time + datetime.timedelta(hours=-5)

class Tag(db.Model):
    tag = db.StringProperty()

class Blog(db.Model):            # Blog Model
    name = db.StringProperty()
    description = db.StringProperty()
    ownerid = db.StringProperty()   # store owner's user_id
    ownername = db.StringProperty()
    created_time = db.DateTimeProperty(auto_now_add=True)

class Image(db.Model):
    """ Image Model, several Image instance can belong to one Post instance """
    image = db.BlobProperty()
    post = db.ReferenceProperty(Post, collection_name = 'images')
    contentType = db.StringProperty()

class Comment(db.Model):
    comment = db.TextProperty(default = "")
    post = db.ReferenceProperty(Post, collection_name = 'comments')
    author = db.TextProperty()
    created_time = db.DateTimeProperty(auto_now_add=True)

def content_filter(str): 
    """ replace links and picturen links in text content with HTML link or picture """
    str = re.sub(r'(https?)(://[\w:;/.?%#&=+-]+)(\.(jpg|png|gif))', imageReplacer, str)
    str = re.sub(r'(?<!")(https?)(://[\w:;/.?%#&=+-]+)', urlReplacer, str)
    str = str.replace('\r\n', '\n')
    str = str.replace('\n','<br />\n')
    str = displayImages(str)
    return str

def urlReplacer(match, limit =40):
    return '<a href="%s">%s</a>' % (match.group(), match.group()[:limit] + ('...' if len(match.group()) > limit else ''))

def imageReplacer(match):
    return '<div><image src="%s" alt="loading image.."></div>' % match.group()

def displayImages(str):
    return re.sub(r'\[img:(.*)\]', r'<img src="/image/\1" style="max-width:400px">', str)


### Handler Function Class ###

class MainPage(webapp2.RequestHandler):
    """ List all blogs info on single page """
    def get(self):
        blogs = Blog.all()
        blogs.order("-created_time")
        user = users.get_current_user()
        if user:
            url = users.create_logout_url('/')
            url_linktext = user.nickname() + ' -> Logout'
        else:
            url = users.create_login_url('/')
            url_linktext = 'Login'

        template_values = {
            'url': url,
            'url_linktext': url_linktext,
            'blogs': blogs
        }
        template = JINJA_ENVIRONMENT.get_template('/templates/bloglist.html')
        self.response.write(template.render(template_values))

class CreateBlog(webapp2.RequestHandler):
    """ Create Blog """
    def get(self):        
        user = users.get_current_user()
        if user:
            template = JINJA_ENVIRONMENT.get_template('/templates/createblog.html')
            self.response.write(template.render())
        else:
            self.redirect(users.create_login_url('/'))
    
    def post(self):
        name = self.request.get('name')
        description = self.request.get('description') 
        user = users.get_current_user()
        ownerid = user.user_id()       # user_id() returns a unique string id for google account user
        ownername = user.nickname()
        if name and description:              
            blog = Blog(name=name, description=description, ownerid=ownerid, ownername = ownername)
            blog.created_time = blog.created_time + datetime.timedelta(hours=-5)
            blog.put()

        self.redirect('/') 

        

class BlogPage(webapp2.RequestHandler):  
    """ Only display posts belong to selected blog entity """
    def get(self, blogkey):
        parentblog = Blog.get_by_id(int(blogkey))    
        posts = Post.all()
        posts.ancestor(parentblog)        
        posts.order("-created_time")

        tag_list = []
        for post in posts:
            for tag in post.tagList():
                if tag_list:
                    isTagExist = False
                    for item in tag_list:
                        if item.tag == tag.tag:
                            isTagExist = True
                            break
                    if not isTagExist:
                        tag_list.append(tag)
                else:
                    tag_list.append(tag)

        cursor = self.request.get('cursor')
        if cursor: 
            posts.with_cursor(start_cursor=cursor)
        items = posts.fetch(10)
        if len(items) < 10:      
            cursor = None     # indicate this is last page
        else:
            cursor = posts.cursor()

        # pass parent blogkey to singleblog page
        template_values = {'blogkey': blogkey,'posts': items, 'cursor': cursor, 'taglist': tag_list}    

        template = JINJA_ENVIRONMENT.get_template('/templates/singleblog.html')
        self.response.write(template.render(template_values))

class TagHandler(webapp2.RequestHandler):
    def get(self, tagkey, blogkey):
        tag = Tag.get(tagkey)   # get tag entity
        parentblog = Blog.get_by_id(int(blogkey))
        posts = Post.all()
        posts.ancestor(parentblog)
        posts.filter('tags', tag.key())
        posts.order("-created_time") 
 
        cursor = self.request.get('cursor')
        if cursor: 
            posts.with_cursor(start_cursor=cursor)
        items = posts.fetch(10)
        if len(items) < 10:      
            cursor = None     # indicate this is last page
        else:
            cursor = posts.cursor()

        # pass parent blogkey to singleblog page
        template_values = {'blogkey': blogkey,'posts': items, 'cursor': cursor}    

        template = JINJA_ENVIRONMENT.get_template('/templates/singleblog.html')
        self.response.write(template.render(template_values))
        

class Postblog(webapp2.RequestHandler):  
    """ Post a new post on a Blog """
    def get(self, blogkey):        # must have get function to render the new html page
        user = users.get_current_user()
        parentblog = Blog.get_by_id(int(blogkey))
        if user:                                    # need to check if the current user is owner
            if parentblog.ownerid == user.user_id():
                template = JINJA_ENVIRONMENT.get_template('/templates/post.html')
                self.response.write(template.render({'blogkey': blogkey}))
            else:
                template = JINJA_ENVIRONMENT.get_template('/templates/error.html')
                self.response.write(template.render({'dir': 'singleblog','key': blogkey}))
        else:
            self.redirect(users.create_login_url('/post/%s' % blogkey))
    
    def post(self, blogkey):           # tag must be separated by comma ','           
        parentblog = Blog.get_by_id(int(blogkey))
        post = Post(parent=parentblog)           # set this new post's belonging blog
        post.title = self.request.get('title')
        post.content = self.request.get('content')
        post.created_time = post.created_time + datetime.timedelta(hours=-5)
        post.modify_time = post.modify_time + datetime.timedelta(hours=-5)
        tags = self.request.get('tags')
        if post.title and post.content:
            taglist = re.split('[,; ]+', tags)
            post.tags = []
            for tagstr in taglist:      # store Tag entity into datastore and they will have key
                tag = Tag.all().filter('tag =', tagstr).get()
                if tag == None:         # if this is not None, then the tag is used before
                    tag = Tag(tag=tagstr)
                    tag.put()
                post.tags.append(tag.key())
            post.put()

        self.redirect('/singleblog/%s' % blogkey)  

class SinglePost(webapp2.RequestHandler):   
    """ Display single post """
    def get(self, postkey):
        singlepost = Post.get(postkey)  # This key is string format, return from post.key() in singleblog.html
        template = JINJA_ENVIRONMENT.get_template('/templates/singlepost.html')
        self.response.write(template.render({'blogkey':singlepost.parent_key().id(),
                                             'postkey': postkey,
                                             'post':singlepost}))

class EditPost(webapp2.RequestHandler):     # Only when edit post that is already exsiting can user add images
    """ Edit Post, content will be prefilled by previous one """
    def get(self, postkey):
        user = users.get_current_user()
        singlepost = Post.get(postkey)
        parentblog = Blog.get_by_id(int(singlepost.parent_key().id()))
        if user:
            if parentblog.ownerid == user.user_id():
                template = JINJA_ENVIRONMENT.get_template('/templates/editpost.html')
                self.response.write(template.render({'postkey':postkey, 
                                                     'pretitle':singlepost.title,
                                                     'precontent':singlepost.content,
                                                     'pretags': singlepost.tagStr(),
                                                     'images': singlepost.images}))
            else:
                template = JINJA_ENVIRONMENT.get_template('/templates/error.html')
                self.response.write(template.render({'dir': 'singlepost','key': postkey}))
        else:
            self.redirect(users.create_login_url('/editpost/%s' % postkey))
    def post(self, postkey):
        singlepost = Post.get(postkey)
        singlepost.title = self.request.get('title')
        singlepost.content = self.request.get('content')
        tags = self.request.get('tags')
        taglist = re.split('[,; ]+', tags)
        singlepost.tags = []
        for tagstr in taglist:      # store Tag entity into datastore and they will have key
            tag = Tag.all().filter('tag =', tagstr).get()
            if tag == None:         # if this is not None, then the tag is used before
                tag = Tag(tag=tagstr)
                tag.put()
            singlepost.tags.append(tag.key())
        
        if self.request.get('file'):
            image = Image()
            image.image = self.request.POST.get('file').file.read()
            image.contentType = self.request.body_file.vars['file'].headers['content-type']
            image.post = singlepost
            image.put()
            singlepost.content = singlepost.content + '\n' + '[img:%s]' % image.key() + '\n'
            
        singlepost.put()     #update entity
        self.redirect('/singlepost/%s' % postkey)

class RssHandler(webapp2.RequestHandler):
    """ Generate RSS for a single blog """
    def get(self, blogkey):
        parentblog = Blog.get_by_id(int(blogkey))    
        posts = Post.all()
        posts.ancestor(parentblog)        
        posts.order("-created_time")
        template = JINJA_ENVIRONMENT.get_template('/templates/rss.xml')
        self.response.write(template.render({'posts': posts}))

class CommentHandler(webapp2.RequestHandler):
    def post(self, postkey):
        if self.request.get("comment") != '':
            comment = Comment()
            comment.comment = self.request.get('comment')
            comment.author = self.request.get('author')
            comment.post = Post.get(postkey)
            comment.put()
        self.redirect('/singlepost/%s' % postkey)

class ImageHandler(webapp2.RequestHandler):
    def get(self, imagekey):
        image = getImage(imagekey)
        self.response.headers['Content-Type'] = image.contentType.encode('utf-8')
        self.response.out.write(image.image)

def getImage(key):
    data = memcache.get(key)
    if data == None:
        data = db.get(key)
        memcache.set(key = key, value = data, time=3600)
    return data

app = webapp2.WSGIApplication([
    ('/', MainPage), 
    ('/createblog', CreateBlog),
    ('/singleblog/(.*)', BlogPage),
    ('/post/(.*)', Postblog), 
    ('/singlepost/(.*)', SinglePost),
    ('/editpost/(.*)', EditPost),
    ('/tag/(.*)/(.*)', TagHandler),
    ('/rss/(.*)', RssHandler),
    ('/image/(.*)', ImageHandler),
    ('/comment/(.*)', CommentHandler)
], debug=True)
