# -*- coding: utf-8 -*-

import urllib
import urllib2
import base64
import gluon.contrib.simplejson as json
from urlparse import urlparse
import os.path
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import re

# TODO store these here?
#basespaceuser1 aTest-1 (app)
client_id     = 'f4e812672009413d809b7caa31aae9b4'
client_secret = 'a23bee7515a54142937d9eb56b7d6659'

#esmith picardSpace app
#client_id     = 'e9ac8de26ae74d2aa7ae313803dc0ca9'
#client_secret = 'f7618095b46145a1bfbe9c4bca8aea38'
#app_session_num = '57aa1ae5dc3d4d26b944d211fb63ff38'

baseSpaceUrl  = 'https://api.cloud-endor.illumina.com/'
version       = 'v1pre3'


def index():
    """
    A user just launched the PicardSpace app
    Retrieve the app session number to identify items that the users selected to analyze
    """
    # display welcome 'flash' dialog and disable menu navigation
    # response.flash = "Welcome to PicardSpace!"    
    response.menu = False
    response.title = "PicardSpace"
    response.subtitle = "Home Page"

    # clear existing session vars 
    session.app_session_num = None
    session.project_num = None
    session.scope = None

    message = "Welcome to PicardSpace! Please log in."
    
    # record app session number if provided
    if (request.get_vars.appsessionuri):
        appsessionuri = request.get_vars.appsessionuri
        session.app_session_num = os.path.basename(appsessionuri)
         
        # exchange app session num for items the user pre-selected in BaseSpace
        bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version,session.app_session_num)
        app_ssn = bs_api.getAppSession()  

        # TODO iterate over all inputs and assemble into master scope string?
        ssn_ref = app_ssn.References[0]
        if (ssn_ref.Type != 'Project'):
            message += " Error - unrecognized reference type " + ssn_ref.Type
        else:
            # get the id and acess string of pre-selected Project
            ref_content = ssn_ref.Content
            session.project_num = ref_content.Id
            session.scope = ref_content.getAccessStr(scope='write')
        
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(user_now_logged_in())
   
    # TODO TEMP show app session num
    if session.app_session_num:
        message += ". (App session num is " + session.app_session_num + ")"
            
    return dict(message=T(message))

@auth.requires_login()
def user_now_logged_in():
    """
    """
    # determine if the user pre-selected a sample/app_result/project to analyze
    if (not session.app_session_num):
        redirect(URL("view_results"))
    else:
        # An app session id was provided, now ask BaseSpace which item(s) the users selected
        redirect(URL(choose_analysis_inputs))
    return dict(message=T(message))


@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """
    response.menu = False
    
    message = ""
    if request.get_vars.message:
        message = request.get_vars.message

    # get all app sessions for the current user
    app_ssns = []
    app_ssns.append( [ 'App Result Name', 'Status', 'Results' ] )
    app_ssn_rows = db(db.app_session.user_id==auth.user_id).select()
    for app_ssn_row in app_ssn_rows:
        a_row = db(db.app_result.id==app_ssn_row.new_app_result_id).select().first()
        if a_row:
            app_ssns.append([ a_row.app_result_name, a_row.status, app_ssn_row.id ])
        
    message += "Launch Analysis -- or View Results!"
    return dict(message=T(message), app_ssns=app_ssns)

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display picard's output from CollectAlignmentMetrics
    """
    response.menu = False
    app_session_id = request.get_vars.app_session_id
    
    f_row = db((db.bs_file.app_session_id==app_session_id)
        & (db.bs_file.io_type=='output')).select().first()
        # TODO select only AlignmentMetrics file, remove first()

    hdr = ""
    aln_tbl = []
    tps_aln_tbl = [["data not available"]]
    if f_row:
        # create file object
        f = File(app_session_id=f_row.app_session_id,
                file_name=f_row.file_name,
                local_path=None,
                file_num=f_row.file_num)
        
        # download file from BaseSpace
        # TODO remove hard-coded path
        local_dir="applications/picardSpace/private/downloads/viewing/" + str(f_row.app_session_id.app_session_num) + "/" 
        try:
            local_path = f.download_file(f_row.file_num, local_dir)
        except:
            return [["Error retrieving file from BaseSpace", "", ""]]
        
        # read local file into array (for display in view)
        with open( local_path, "r") as ALN_QC:

            # get picard output header - collect lines finding line starting with 'CATEGORY'
            line = ALN_QC.readline()
            while not re.match("CATEGORY", line):
                hdr += line
                line = ALN_QC.readline()

            # get picard metric data (and table headings)
            aln_tbl.append(line.rstrip().split("\t"))
            for line in ALN_QC:
                if line.rstrip():
                    aln_tbl.append(line.rstrip().split("\t"))
            ALN_QC.close()

            # transpose list (for viewing - so it is long instead of wide)(now its a tuple)
            tps_aln_tbl = zip(*aln_tbl)

    # TODO check that user is correct (could jump to this page as another user)
    return(dict(aln_tbl=tps_aln_tbl, hdr=hdr))


@auth.requires_login()
def choose_analysis_inputs():
    """
    Offers the user choice of files to analyze, and ability to launch analysis (including download)
    """
    response.menu = False
    
    # TODO handle no pre-selected items from app_session_num

    # get project to select items from
    app_session_num = session.app_session_num
    project_num = session.project_num
    
    # Given an item name to analyze, get an authorization code (which we'll exchange for an auth token)         
    # TODO cheating here for now -- also using session vars; make these pass from view back to  get_auth_code()
    session.orig_app_result_num = 9995
#    project_num = 51
    session.file_num = 2351949
    session.appresult_name = "Picard Alignment Metrics"
    session.appresult_description = "Picard aln QC"

    return dict(project_num=T(str(project_num)),
        orig_app_result_num=T(str(session.orig_app_result_num)),
        file_num=T(str(session.file_num)),
        appresult_name=T(str(session.appresult_name)),
        appresult_description=T(str(session.appresult_description)))


@auth.requires_login()
def get_auth_code():
    """
    Given an app session number, exchange this via BaseSpace API for item names to analyze
    """
    app_session_num = session.app_session_num
    # TODO these shouldn't be session vars?
    project_num = session.project_num
    orig_app_result_num = session.orig_app_result_num
    file_num = session.file_num
    
    # TODO move to choose_analysis_inputs
    # create app session in db
    app_session_id = db.app_session.insert(app_session_num=app_session_num,
        project_num=project_num,
        orig_app_result_num=orig_app_result_num,
        file_num=file_num)
        
    scope = 'write project ' + str(project_num)    
    #scope = 'read appresult ' + str(orig_app_result_num) + ',write project ' + str(project_num)
    redirect_uri = 'http://localhost:8000/picardSpace/default/start_analysis'

    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, app_session_num)
    # TODO remove state var here (app session num is session var)?
    userUrl = bs_api.getWebVerificationCode(scope,redirect_uri,state=app_session_num)
    redirect(userUrl)


@auth.requires_login()
def start_analysis():
    """
    Given an authorization code, exchange this for an authorization token
    Then use the token to access the underlying data of item(s)
    """
    # get authorization code from response url
    if (request.get_vars.error):
        message = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(message=T(message))
        
    # record auth_code and app session num from 'state' to connect scope request with auth token (getting next)
    auth_code = request.get_vars.code
    f = request.get_vars.state
        
    # exchange authorization code for auth token
    app_session_num = session.app_session_num
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version,app_session_num)
    bs_api.updatePrivileges(auth_code)      
    access_token =  bs_api.getAccessToken()      

    # ensure the current app user is the same as the current BaseSpace user        
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    cur_user_id = user_row.username
    bs_user = bs_api.getUserById('current')
    if (bs_user.Id != cur_user_id):
        # TODO how to handle this error?
        message = "Error - Current user_id is " + str(cur_user_id) + " while current BaseSpace user id is " +str(bs_user.Id)
        return dict(message=T(message))
   
    # update user's access token in user table
    user_row.update_record(access_token=access_token)

    # get session id from db
    app_ssn_row = db(db.app_session.app_session_num==app_session_num).select().first()   
    
    # add new AppResult to db            
    app_result_id = db.app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=session.project_num,
        app_result_name=session.app_result_name,
      #      app_result_num=self.app_result_num,
        description=session.appresult_description,
        status="queued for download")      
    db.commit()

    # update app session with user id, and new appresult
    # TODO include user_id when creating app session in db (above)?
    app_ssn_row.update_record(user_id=user_row.id, new_app_result_id=app_result_id)
    db.commit()

    # add input (BAM) file to db
    bs_file_id = db.bs_file.insert(
        app_result_id=app_result_id,
        app_session_id=app_ssn_row.id,
        file_num=app_ssn_row.file_num, 
        io_type="input")
        
    # add App Result to download queue
    db.download_queue.insert(status='pending', app_result_id=app_result_id)

    # clear session vars
    session.app_session_num = None
    session.project_num = None
    session.scope = None  
    session.appresult_name = None
    session.appresult_description = None                                

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis is Started!')))
                              
    message = "welcome back from getting your auth token: " + access_token + " - now we're getting actual BS data!"
    return dict(message=T(message))


# for user authentication
def user(): return dict(form=auth())
