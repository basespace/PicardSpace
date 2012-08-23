# -*- coding: utf-8 -*-

import urllib
import urllib2
import base64
import gluon.contrib.simplejson as json
from urlparse import urlparse
import os.path
from BaseSpacePy.api.BaseSpaceAuth import BaseSpaceAuth

# TODO store these here?
#basespaceuser1 aTest-1 (app)
client_id     = 'f4e812672009413d809b7caa31aae9b4'
client_secret = 'a23bee7515a54142937d9eb56b7d6659'

#esmith picardSpace app
#client_id     = 'e9ac8de26ae74d2aa7ae313803dc0ca9'
#client_secret = 'f7618095b46145a1bfbe9c4bca8aea38'
#app_action_num = '57aa1ae5dc3d4d26b944d211fb63ff38'

baseSpaceUrl  = 'https://api.cloud-endor.illumina.com/'
version       = 'v1pre2/'


def index():
    """
    A user just launched the PicardSpace app
    Retrieve the app_action_num to identify items that the users selected to analyze
    """
    response.flash = "Welcome to PicardSpace!"    
    
    # record app action number if provided
    if (request.get_vars.actionuri):
        actionuri = request.get_vars.actionuri
        app_action_num = os.path.basename(actionuri)
        session.app_action_num = app_action_num

    message = "Welcome to PicardSpace"
    if session.app_action_num:
        message += ". App action num is " + session.app_action_num
            
    return dict(message=T(message))


def user_now_logged_in():
    """
    """
        # determine if the user pre-selected a sample/analysis/project to analyze
    if (not session.app_action_num):
    #if (not request.get_vars.actionuri):
        # TODO - present user with choice of BaseSpace items
        message = "No actionurl was found - which samples should I analyze??"
    else:
        # An action_id was provided, now ask BaseSpace which item(s) the users selected
        #action = request.get_vars.action
        #actionuri = request.get_vars.actionuri
        #app_action_num = os.path.basename(actionuri)
        #return_uri = request.get_vars.return_uri
        redirect(URL(trade_action_id_for_items, vars=dict(app_action_num=session.app_action_num)))
    return dict(message=T(message))

def trade_action_id_for_items():
    """
    Given an app action id, exchange this via BaseSpace API for item names to analyze
    """
    app_action_num = request.vars.app_action_num
    #return_uri = request.vars.return_id
    
    # exchange app_action_id for items the user pre-selected in BaseSpace
    bs_auth = BaseSpaceAuth(client_id,client_secret,baseSpaceUrl,version)
    app_launch = bs_auth.getAppTrigger(app_action_num)  
    app_inputs = app_launch.getLaunchType()

    # TODO iterate over all inputs and assemble into master scope string
    proj = app_inputs[1][-1]
    proj.getAccessStr(scope='write')
    project_num = proj.Id
    #scope = proj.getAccessStr(scope='write')
   
    # Given an item name to analyze, get an authorization code (which we'll exchange for an auth token)         
    # TODO change these to session vars (instead of in db before user OKs data access?)
    analysis_num = 9995
#    project_num = 51
    file_num = 2351949
    #file_num = [ file_num ]

    app_session_id = db.app_session.insert(app_action_num=app_action_num,
        project_num=project_num,
        analysis_num=analysis_num,
        file_num=file_num)
        
    scope = 'read analysis ' + str(analysis_num) + ',write project ' + str(project_num)
    redirect_uri = 'http://localhost:8000/picardSpace/default/startanalysis'

    bs_auth = BaseSpaceAuth(client_id,client_secret,baseSpaceUrl,version)
    userUrl = bs_auth.getWebVerificationCode(scope,redirect_uri,state=app_action_num)
    redirect(userUrl)


def startanalysis():
    """
    Given an authorization code, exchange this for an authorization token
    Then use the token to access the underlying data of item(s)
    """
    # get authorization code from response url
    if (request.get_vars.error):
        message = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(message=T(message))
        
    # record auth_code and app_action from 'state' to connect scope request with auth token (getting next)
    auth_code = request.get_vars.code
    app_action_num = request.get_vars.state
        
    # exchange authorization code for auth token
    bs_auth = BaseSpaceAuth(client_id,client_secret,baseSpaceUrl,version)   
    myAPI = bs_auth.getBaseSpaceApi(auth_code)
    access_token =  myAPI.getAccessToken()

    # check that the user is logged in TODO check this upstream of here
    if not auth.user_id:
        message = "Please log into PicardSpace before launching an analysis"
        return dict(message=T(message))       

    # ensure the current app user is the same as the current BaseSpace user        
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    cur_user_id = user_row.username
    bs_user = myAPI.getUserById('current')
    if (bs_user.Id != cur_user_id):
        # TODO how to handle this error?
        message = "Error - Current user_id is " + str(cur_user_id) + " while current BaseSpace user id is " +str(bs_user.Id)
        return dict(message=T(message))
                                      
    # update user's access token in user table
    user_row.update_record(password=access_token)

    # create analyis entries in db
    app_ssn_row = db(db.app_session.app_action_num==app_action_num).select().first()    

    # update app session with user id
    app_ssn_row.update_record(user_id=user_row.id)
    db.commit()

    # create file entry(s) in db
    bs_file_id = db.bs_file.insert(app_session_id=app_ssn_row.id,
        file_num=app_ssn_row.file_num)
        
    # add file to download queue
    db.download_queue.insert(status='pending', bs_file_id = bs_file_id)
                              
    message = "welcome back from getting your auth token: " + access_token + " - now we're getting actual BS data!"
    return dict(message=T(message))


# for user authentication
def user(): return dict(form=auth())
