#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect,jsonify, url_for, flash

from sqlalchemy import create_engine, asc, desc
from sqlalchemy.orm import sessionmaker
from category_database_setup import Base, Category, CategoryItem, User

from flask import session as login_session
import random, string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "restaurant app"

#Connect to Database and create database session
engine = create_engine('sqlite:///tamimcategoryapp.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print ('Access Token is None')
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print ('In gdisconnect access token is %s' % access_token)
    print ('User name is: ')
    print (login_session['username'])
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print ('result is ')
    print (result)
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/login')
def showLogin():
  state = ''.join(random.choice(string.ascii_uppercase+string.digits) for x in range(32))
  login_session['state']=state
  return render_template('login1.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1].decode('utf-8'))
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print ("Token's client ID does not match app's.")
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
        login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print ("done!")
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/category/JSON')
def categoryJSON():
    categories = session.query(Category).all()
    return jsonify(categories = [r.serialize for r in categories])


#Catalog main page
@app.route('/')
def mainPage():
    categories = session.query(Category).order_by(asc(Category.name))
    items = session.query(CategoryItem).order_by(desc(CategoryItem.created_date)).limit(5).all()
    if 'username' not in login_session:
        return render_template('category.html', categories = categories, items = items)
    else:
        return render_template('loggedCategory.html', categories = categories, items = items)


@app.route('/showItems/<int:category_id>')
def showItems(category_id):
    category = session.query(Category).filter_by(id = category_id).one()
    items = session.query(CategoryItem).filter_by(category_id = category_id).all()
    # creator = getUserInfo(category.user_id)
    if 'username' not in login_session:
        return render_template('showitems.html', items = items, category = category)
    else:
        return render_template('loggedshowitems.html', items = items, category = category)


@app.route('/displayItem/<int:item_id>')
def displayItem(item_id):
    item = session.query(CategoryItem).filter_by(id = item_id).one()
    if 'username' not in login_session:
        return render_template('displayitem.html', item = item)
    else:
        return render_template('loggeddisplayitem.html', item = item)


@app.route('/newItem/<int:category_id>', methods = ['GET', 'POST'])
def newItem(category_id):
    category = session.query(Category).filter_by(id = category_id).one()
    if request.method == 'POST':
        newitem = CategoryItem(name = request.form['name'], description = request.form['description'], category_id = category_id)
        session.add(newitem)
        session.commit()
        flash('New item %s added' % (newitem.name))
        return redirect(url_for('showItems', category_id = category_id))
    else:
        return render_template('newitem.html', category_id = category_id)

@app.route('/addItem', methods = ['GET', 'POST'])
def addItem():
    if request.method == 'POST':
        category_name = request.form['category']
        category = session.query(Category).filter_by(name = category_name).one()
        newitem = CategoryItem(name = request.form['name'], description = request.form['description'], category_id = category.id)
        session.add(newitem)
        session.commit()
        flash('New item %s added' % (newitem.name))
        return redirect(url_for('mainPage'))
    else:
        return render_template('addfrommain.html')


@app.route('/editItem/<int:item_id>', methods=['GET','POST'])
def editItem(item_id):
    editedItem = session.query(CategoryItem).filter_by(id = item_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        session.add(editedItem)
        session.commit()
        flash('Item %s edited' % (editedItem.name))
        return redirect(url_for('displayItem', item_id = item_id))
    else:
        return render_template('editItem.html', item_id = item_id, item = editedItem)


@app.route('/deleteItem/<int:item_id>', methods=['GET','POST'])
def deleteItem(item_id):
    deletedItem = session.query(CategoryItem).filter_by(id = item_id).one()
    if request.method == 'POST':
        session.delete(deletedItem)
        session.commit()
        flash('Item Successfully Deleted')
        return redirect(url_for('mainPage'))
    else:
        return render_template('deleteItem.html', item = deletedItem)


if __name__ == '__main__':
  app.secret_key = 'super_secret_key'
  app.debug = True
  app.run(host = '0.0.0.0', port = 8000)