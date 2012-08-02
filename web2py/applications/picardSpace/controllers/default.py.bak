# -*- coding: utf-8 -*-

import urllib
import urllib2
import base64
import gluon.contrib.simplejson as json
from urlparse import urlparse
import os.path

# TODO store this here?
client_id = 'e9ac8de26ae74d2aa7ae313803dc0ca9'
client_secret = 'f7618095b46145a1bfbe9c4bca8aea38'


def index():
    """
    A user just launched the PicardSpace app
    Determine if the user pre-selected a sample/analysis/project to analyze
    """    
    response.flash = "Welcome to PicardSpace!"    
    
    if (not request.get_vars.action_id):
        # An action_id was not provided, so the user didn't indicate which BaseSpace items to analyze
        # TODO - present user with choice of BaseSpace items; for now use this TEMP redirect:
        redirect(URL(trade_action_id_for_items, vars=dict(app_action_id="none",return_uri="none")))
    else:
        # An action_id was provided, now ask BaseSpace which item(s) the users selected
        app_action_id = request.get_vars.action_id
        return_uri = request.get_vars.return_uri
        redirect(URL(trade_action_id_for_items, vars=dict(app_action_id=app_action_id, return_uri=return_uri)))


def trade_action_id_for_items():
    """
    Given an app action id, exchange this via BaseSpace API for item names to analyze
    """
    app_action_id = request.vars.app_action_id
    return_uri = request.vars.return_id
    # TODO TEMP    
    app_action_id = '57aa1ae5dc3d4d26b944d211fb63ff38'        
                
    headers = { 'Authorization': 'Basic ' + base64.b64encode(client_id + ':' + client_secret) }
    url = 'http://api.cloud-endor.illumina.com/v1pre2/applicationactions/' + app_action_id
    req = urllib2.Request(url, headers)
    # TODO parse item(s) from response and store them for accessing after we get auth token
    
    # Given an item name to analyze, get an authorization code (which we'll exchange for an auth token)         
    # TODO - need to sync analysis_num here with adding to db below after getting token
    analysis_num = 9995
    scope = 'read+analysis+' + str(analysis_num)  # TODO add urllib's urlencode? or quote() here?

    redirect_uri = 'http://localhost:8000/picardSpace/default/startanalysis'
    auth_uri = 'https://cloud-endor.illumina.com/oauth/authorize?client_id=' + client_id + '&scope=' + scope + '&redirect_uri=' + redirect_uri +   '&response_type=code'
    redirect(auth_uri)


def startanalysis():
    """
    Given an authorization code, exchange this for an authorization token
    Then use the token to access the underlying data of item(s)
    """
    # get authorization code from response url
    if (request.get_vars.error):
        # TODO how to detect and handle error here?
        message = request.get_vars.error + ": " + request.get_vars.error_message
        auth_uri = 'http://www.google.com'
    else:
        # exchange authorization code for auth token
        auth_code = request.get_vars.code        
        # TODO parse optional 'state'?
        
        # perform a POST with http basic authenication that includes the auth code                        
        redirect_uri = 'http://localhost:8000/picardSpace/default/startanalysis' # redirect of "application"        
        url = 'https://api.cloud-endor.illumina.com/v1pre2/oauthv2/token?code=' + auth_code + '&redirect_uri=' + redirect_uri + '&grant_type=authorization_code'                
        args = "" # req for POST
        headers = {}
        headers['content-type'] = 'application/x-www-form-urlencoded'
        headers['Authorization'] = 'Basic '+ base64.b64encode(client_id + ':' + client_secret)        
        req = urllib2.Request(url,args, headers)
        resp = urllib2.urlopen(req)
        
        # parse response for access_token
        resp_data = json.loads(resp.read())
        if 'access_token' in resp_data:
            access_token = resp_data['access_token']
            # TODO is it secure to pass the access_token like this?
            redirect(URL(get_bs_data, vars=dict(access_token=access_token)))            
        else:
            # there was an error - no access token was returned
            if ('error_code' in resp_data) and ('error_description' in resp_data):
                message =  "Error - received error code " + resp_data['error_code']
                message += " with description: " + resp_data['error_description']
            else:
                # TODO handle this error better
                message = "Unexpected error"        
           
    return dict(message=T(message))

    
def get_bs_data():
    """
    Using the access token, get underlying BaseSpace data of item(s) to analyze
    """    
    access_token = request.vars.access_token

    # TODO how to sync scope from request above with adding it to db here?
    # create analyis entries in db
    action_id = "TODO"
    project_num = 51
    analysis_num = 9995
    analysis_name = 'Resequencing'
    analysis_id = db.analysis.insert(action_id=action_id, 
        project_num=project_num,
        analysis_num=analysis_num,
        analysis_name=analysis_name,
        access_token=access_token)
    
    # create file entry(s) in db
    file_num = 2351949
    file_name = 's_G1.1.chrY.bam'
    bs_file_id = db.bs_file.insert(analysis_id=analysis_id,
        file_num=file_num,
        file_name=file_name)

    # add file to download queue
    db.download_queue.insert(status='pending', bs_file_id = bs_file_id)
                             
#    file 21353 is test BAM
#    file 21305 is test VCF
        
#    aws_url = resp.geturl()    
#    hdr = resp.info()    
#    content = resp.read()
        
#    resp_data = json.loads(content)    
#    message += " RESPONSE: "
#    for key,val in resp_data.iteritems():
#        message += str(key) + ": " + str(val) + " "
    
    message = "welcome back from getting your auth token: " + access_token + " - now we're getting actual BS data!"
    return dict(message=T(message))
