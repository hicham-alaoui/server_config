#!/usr/bin/env python


from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from properties_db import Base, Area, Property, User

# Import Login session
from flask import session as login_session
import random
import string

# imports for gconnect
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

# import login decorator
from functools import wraps

app = Flask(__name__)

CLIENT_ID = json.loads(open('client_secrets.json', 'r')
                       .read())['web']['client_id']
APPLICATION_NAME = "properties"

engine = create_engine('sqlite:///properties_list.db')
Base.metadata.bind = engine

DBsession = sessionmaker(bind=engine)
session = DBsession()

# create a state token to request forgery.
# store it in the session for later validation


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_name' not in login_session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login')
def gLogin():
    state = ''.join(random.choice(string.ascii_uppercase +
                                  string.digits)for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application-json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # upgrade the authorization code in credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps('Failed to upgrade\
        the authorization code'), 401)
        response.headers['Content-Type'] = 'application-json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1].decode("utf-8"))
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
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response
    # Access token within the app
    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is\
        already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.

    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id
    response = make_response(json.dumps('Succesfully connected users', 200))

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()
    login_session['provider'] = 'google'
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # See if user exists or if it doesn't make a new one
    print 'User email is' + str(login_session['email'])
    user_id = getUserID(login_session['email'])
    if user_id:
        print 'Existing user#' + str(user_id) + 'matches this email'
    else:
        user_id = createUser(login_session)
        print 'New user_id#' + str(user_id) + 'created'
    login_session['user_id'] = user_id
    print 'Login session is tied to :id#' + str(login_session['user_id'])

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 100px; height: 100px;border-radius:150px;- \
      webkit-border-radius:150px;-moz-border-radius: 150px;">'
    flash("Logged in as %s" % login_session['username'])
    print "done!"
    return output
    user_id = login_session


# Helper Functions
def createUser(login_session):
    newUser = User(name=login_session['username'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).first()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).first()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).first()
        return user.id
    except:
        return None


# DISCONNECT - Revoke a current user's token and reset their login_session.
@app.route('/gdisconnect')
def gdisconnect():
    # only disconnect a connected User
    access_token = login_session.get('access_token')
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    if access_token is None:
        print'Access Token is None'
        response = make_response(json.dumps('Current user not connected'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is'
    print result
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:

        response = make_response(json.dumps('Failed to revoke token\
                                             for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/logout')
def logout():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['access_token']
            del login_session['username']
            del login_session['email']
            del login_session['picture']
            del login_session['user_id']
            del login_session['provider']
        flash("you have succesfully been logout")
        return redirect(url_for('allAreas'))
    else:
        flash("you were not logged in")
        return redirect(url_for('allAreas'))


# JSON API Endpoint for all properties
@app.route('/areas/<int:area_id>/properties/JSON')
def areaPropertiesJSON(area_id):
    area = session.query(Area).filter_by(id=area_id).one()
    properties = session.query(Property).filter_by(area_id=area.id).all()
    return jsonify(AreaProperties=[i.serialize for i in properties])


# JSON API Endpoint for all properties
@app.route('/properties/JSON')
def allPropertiesJSON():
    all_properties = session.query(Property).all()
    return jsonify(allProperties=[p.serialize for p in all_properties])


# JSON API Endpoint for a specific property
@app.route('/areas/<int:area_id>/properties/<int:property_id>/JSON')
def singlePropertyJSON(area_id, property_id):
    oneProperty = session.query(Property).filter_by(id=property_id).one()
    return jsonify(Property=oneProperty.serialize)


# Areas page
@app.route('/')
@app.route('/areas/')
def allAreas():
    areas = session.query(Area).order_by(asc(Area.name))
    if 'username' not in login_session:
        return render_template('public_areas.html', all_areas=areas)
    else:
        return render_template('areas.html', all_areas=areas)


# Create a new area
@app.route('/areas/new/', methods=['GET', 'POST'])
def newArea():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newArea = Area(name=request.form['name'],
                       user_id=login_session['user_id'])
        session.add(newArea)
        flash('New Area %s Successfully Created' % newArea.name)
        session.commit()
        return redirect(url_for('allAreas'))
    else:
        return render_template('new_area.html')


@app.route('/areas/<int:area_id>/edit/', methods=['GET', 'POST'])
def editArea(area_id):
    if 'username' not in login_session:
        return redirect('/login')
    editarea = session.query(Area).filter_by(id=area_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if editarea.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('Sorry! You can only\
        edit the items associated with your id.\
        Click on the backward arrow in your browser\
        to re-open the previous page');}</script><body onload='myFunction()'>"
    if request.method == 'POST':
        if request.form['name']:
            editarea.name = request.form['name']
            flash("Area edited")
            return redirect(url_for('allAreas'))
    else:
        return render_template('edit_area.html', i=editarea)


# Delete an area
@app.route('/areas/<int:area_id>/delete/', methods=['GET', 'POST'])
def deleteArea(area_id):
    deleteArea = session.query(Area).filter_by(id=area_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if deleteArea.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('Sorry! You can only delete the items\
       associated with your id.\ Click on the backward arrow in your browser\
       to re-open the previous page');}\
       </script><body onLoad = 'myFunction()''>"
    if request.method == 'POST':
        session.delete(deleteArea)
        flash("Area deleted")
        session.commit()
        return redirect(url_for('allAreas', area_id=area_id))
    else:
        return render_template('delete_area.html', i=deleteArea)


# Areas page
@app.route('/areas/<int:area_id>/')
@app.route('/areas/<int:area_id>/properties/')
def allProperties(area_id):
    areas = session.query(Area).filter_by(id=area_id).first()
    creator = getUserInfo(areas.user_id)
    list = session.query(Property).filter_by(area_id=area_id).all()

    if 'username' not in login_session:
        return render_template('public_properties.html',
                               list=list, area=areas, creator=creator)
    else:
        return render_template('properties.html',
                               list=list, area=areas, creator=creator)


# Add new property
@app.route('/areas/<int:area_id>/properties/new/', methods=['GET', 'POST'])
def newProperty(area_id):
    if 'username' not in login_session:
        return redirect('/login')
    area = session.query(Area).filter_by(id=area_id).one()
    if request.method == 'POST':
        new_property = Property(address=request.form['address'],
                                description=request.form['description'],
                                city=request.form['city'],
                                price=request.form['price'],
                                area_id=area_id, user_id=area.user_id)
        session.add(new_property)
        session.commit()
        flash("New property created")
        return redirect(url_for('allProperties', area_id=area_id))
    else:
        return render_template('new_property.html', area_id=area_id)


# Edit property
@app.route('/areas/<int:area_id>/properties/<int:property_id>/edit',
           methods=['GET', 'POST'])
def editProperty(area_id, property_id):
    if 'username' not in login_session:
        return redirect('/login')
    edit_property = session.query(Property).filter_by(id=property_id).one()
    area = session.query(Area).filter_by(id=area_id).one()
    if login_session['user_id'] != area.user_id:
        return "<script>function myFunction() {alert ('Sorry! You can only\
        edit the items associated with your id.\ Click on the backward arrow\
        in your browser\ to re-open the previous page');}\
        </script><body onload='myFunction()''>"

    if request.method == 'POST':
        if request.form['address']:
            edit_property.address = request.form['address']
        if request.form['description']:
            edit_property.description = request.form['description']
        if request.form['city']:
            edit_property.city = request.form['city']
        if request.form['price']:
            edit_property.price = request.form['price']
        session.add(edit_property)
        session.commit()
        flash('Property Details Edited')
        return redirect(url_for('allProperties', area_id=area_id))
    else:
        return render_template('edit_property.html', area_id=area_id,
                               property_id=property_id,
                               editProperty=edit_property)


# Delete a property
@app.route('/areas/<int:area_id>/properties/<int:property_id>/delete',
           methods=['GET', 'POST'])
def deleteProperty(area_id, property_id):
    if 'username' not in login_session:
        return redirect('/login')
    area = session.query(Area).filter_by(id=area_id).one()
    delete_property = session.query(Property).filter_by(id=property_id).one()
    if login_session['user_id'] != area.user_id:
        return "<script>function myFunction() {alert ('Sorry! You can\
       only delete the items associated with your id.\ Click on the\
       backward arrow in your browser\ to re-open the previous page');}\
       </script><body onload='myFunction()''>"
    if request.method == 'POST':
        session.delete(delete_property)
        session.commit()
        flash('Property Successfully Deleted')
        return redirect(url_for('allAreas', area_id=area_id))
    else:
        return render_template('delete_property.html',
                               delete_property=delete_property)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = False
    app.run()
