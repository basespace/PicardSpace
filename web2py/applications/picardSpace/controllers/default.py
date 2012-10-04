# -*- coding: utf-8 -*-

import urllib
import urllib2
import base64
import gluon.contrib.simplejson as json
from urlparse import urlparse
import os.path
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import re
from picardSpace import File

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
    response.menu = False
    response.title = "PicardSpace"
    response.subtitle = "Home Page"

    # clear existing session vars 
    session.app_session_num = None
    session.project_num = None
    session.scope = None

    main_msg = 'Welcome to PicardSpace'
    scnd_msg = 'Please log in'
    err_msg  = ''
    
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
            err_msg += "Error - unrecognized reference type " + ssn_ref.Type + ". "
        else:
            # get the project num and access string of pre-selected Project
            ref_content = ssn_ref.Content
            session.project_num = ref_content.Id
            session.scope = ref_content.getAccessStr(scope='read')
            
            # create app_session in db
            app_session_id = db.app_session.insert(app_session_num=session.app_session_num,
                project_num=session.project_num,
                #user_id=auth.user_id,
                date_created=app_ssn.DateCreated) 
        
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(user_now_logged_in())
   
    # TODO TEMP show app session num
    if session.app_session_num:
        err_msg += "(App session num is " + session.app_session_num + ")"
            
    return dict(main_msg=T(main_msg), scnd_msg=T(scnd_msg), err_msg=T(err_msg))


@auth.requires_login()
def user_now_logged_in():
    """
    Just determined that the user is logged into picardSpace; if a project context was provided, redirect to choose inputs flow, otherwise redirect to view results page
    """
    # determine if the user pre-selected a sample/app_result/project to analyze
    if (not session.app_session_num):
        redirect(URL('view_results'))
    else:
        # an app session num was provided, now ask BaseSpace which item(s) the users selected        
        # update app session with user info
        app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
        app_ssn_row.update_record(user_id=auth.user_id)

        redirect(URL('confirm_session_token'))
    return dict(message=T(message))


@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """
    response.menu = False
    
    # if arriving from just-launched analysis, display msg 'just launched'
    message = ""
    if request.get_vars.message:
        message = request.get_vars.message

    # get BaseSpace API
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num, user_row.access_token)        
    
    # get all app results for the current user
    app_ssns = []
    
    ssn_rows = db(db.app_session.user_id==auth.user_id).select(orderby=~db.app_session.date_created)
    for ssn_row in ssn_rows:
        rslt_rows = db(db.app_result.app_session_id==ssn_row.id).select()

        # get project, sample, and file names for each AppResult    
        for rslt_row in rslt_rows:          
            proj = bs_api.getProjectById(rslt_row.project_num)
            sample_name = "unknown"
            if (rslt_row.sample_num):
                sample = bs_api.getSampleById(rslt_row.sample_num)
                sample_name = sample.Name
            
            # getting input BAM file here (restricted to single input file)
            file_row = db((db.bs_file.app_result_id==rslt_row.id) & (db.bs_file.io_type=='input')).select().first()
            bs_file = bs_api.getFileById(file_row.file_num)

            app_ssns.append( { 'app_result_name':rslt_row.app_result_name, 'sample_name':sample_name, 'file_name':bs_file.Name, 'project_name':proj.Name, 'status':rslt_row.status, 'app_session_id':ssn_row.id, 'notes':rslt_row.message, 'date_created':ssn_row.date_created } )
        
    return dict(message=T(message), app_ssns=app_ssns)

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display picard's output from CollectAlignmentMetrics
    """
    response.menu = False
    app_session_id = request.get_vars.app_session_id
    
    # get sample name
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num, user_row.access_token)        
    ar_row = db(db.app_result.app_session_id==app_session_id).select().first()
    sample_num = ar_row.sample_num
    sample = bs_api.getSampleById(sample_num)
    
    f_row = db((db.bs_file.app_session_id==app_session_id)
        & (db.bs_file.io_type=='output')).select().first()
        # TODO select only AlignmentMetrics file, remove first()

    hdr = ""
    aln_tbl = []
    tps_aln_tbl = [["data not available"]]
    file_name = "unknown"
    if f_row:
        file_name = f_row.file_name
        
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
    return(dict(aln_tbl=tps_aln_tbl, hdr=hdr, sample_name=sample.Name, file_name=file_name))


@auth.requires_login()
def confirm_session_token():
    """
    Check that we have an access token for the current session/project
    (if user was already logged in, and launches from BaseSpace with a new project context)
    """
    response.menu = False

    # get project to select items from
    app_session_num = session.app_session_num
    project_num = session.project_num
    
    # if the session num is new, need to update token with browse access
    if db(db.app_session.app_session_num==session.app_session_num).isempty():
        session.return_url = 'choose_analysis_inputs'
        session.scope = 'read'
        redirect('get_auth_code')
    else:
        redirect('choose_analysis_inputs')


@auth.requires_login()
def choose_analysis_inputs():
    """
    Offers the user choice of files to analyze
    """
    response.menu = False
    # TODO handle no pre-selected items from app_session_num?

    # get project to select items from
    app_session_num = session.app_session_num
    project_num = session.project_num

    # get name of project from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num, user_row.access_token)        
    proj = bs_api.getProjectById(session.project_num)
    project_name = proj.Name    

    return dict(project_name=T(str(project_name)))


@auth.requires_login()
def confirm_analysis_inputs():
    """
    Confirms user's choice of file to analyze; offers naming app result and launch button
    """
    response.menu = False
    
    # get file_num and app_result_num that user selected
    session.file_num = request.get_vars.file_num
    orig_app_result_num = request.get_vars.app_result_num
    
    # TODO what do with orig app result num?
    #session.orig_app_result_num = 9995
    # project_num = 51
    # session.file_num = 2351949
    # TODO make these user inputs in the view?
#    session.app_result_name = "Picard Alignment Metrics"
#    session.app_result_description = "Picard aln QC"

    # get name of file and project (and sample, future) from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num, user_row.access_token)        
    project = bs_api.getProjectById(session.project_num)
    bs_file = bs_api.getFileById(session.file_num)
    app_ssn = bs_api.getAppSession(session.app_session_num)
    
    # get sample num and name from AppResult, if present
    app_result = bs_api.getAppResultById(orig_app_result_num)
    samples_ids = app_result.getReferencedSamplesIds()
    sample_name = "unknown"
    if samples_ids:
        session.sample_num = samples_ids[0]
        sample = bs_api.getSampleById(session.sample_num) 
        sample_name = sample.Name       

    # TODO skip this and depend on creating File in db in start_analysis()??
    # update app session with user's file choice
    app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
    app_ssn_row.update_record(file_num=session.file_num)

    # set scope for getting access token and url to redirect to afterwards
    session.return_url = 'start_analysis'
    session.scope = 'write'

    return dict(project_num=T(str(session.project_num)),
        file_num=T(str(session.file_num)),
        # TODO above fields only needed for testing
        sample_name=T(str(sample_name)),
        file_name=T(str(bs_file.Name)),
        project_name=T(str(project.Name)))        


@auth.requires_login()
def get_auth_code():
    """
    Given an app session number, exchange this via BaseSpace API for item names to analyze
    """                    
    # TODO get post var 'appresult_name', if present, and store in db
    if (request.post_vars.app_result_name):
        session.app_result_name = request.post_vars.app_result_name
    
    scope = session.scope + ' project ' + str(session.project_num)
    redirect_uri = 'http://localhost:8000/picardSpace/default/get_access_token'

    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num)
    # TODO state needed here?
    userUrl = bs_api.getWebVerificationCode(scope,redirect_uri,state=session.app_session_num)
    redirect(userUrl)


@auth.requires_login()
def get_access_token():
    """
    Given an authorization code, exchange this for an access token
    """
    # get authorization code from response url
    if (request.get_vars.error):
        message = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(message=T(message))
        
    # record auth_code and app session num from 'state' to connect scope request with auth token (getting next)
    auth_code = request.get_vars.code
    #f = request.get_vars.state
        
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

    # go to url specified by original call to get token
    redirect(URL(session.return_url))
    

@auth.requires_login()
def start_analysis():
    """
    Create an app result in BaseSpace and the local db, then queue the input BAM file for download from BaseSpace
    """
    # get session id and current user id from db
    app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()
                 
    # add new AppResult to BaseSpace
    bs_api = BaseSpaceAPI(client_id, client_secret, baseSpaceUrl, version, app_ssn_row.app_session_num, user_row.access_token)
    project = bs_api.getProjectById(session.project_num)
    sample = bs_api.getSampleById(session.sample_num)
    app_result = project.createAppResult(bs_api, session.app_result_name, session.app_result_description, appSessionId=app_ssn_row.app_session_num, samples=[ sample ] )
        
    # add new AppResult to db            
    app_result_id = db.app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=session.project_num,
        app_result_name=session.app_result_name,
        app_result_num=app_result.Id,
        sample_num=session.sample_num,
        description=session.app_result_description,
        status="queued for download",
        message="none")      
    db.commit()

    # update app session with user id
    # TODO include user_id when creating app session in db (above)?
    #app_ssn_row.update_record(user_id=user_row.id)
    #db.commit()

    # add input BAM file to db
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
    session.app_result_name = None
    session.app_result_description = None                                

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis Has Started!')))
                              
    message = "welcome back from getting your auth token: " + access_token + " - now we're getting actual BS data!"
    return dict(message=T(message))


def browse_bs_app_results():
    """
    Return an html list of BaseSpace data (for display with JQuery File Tree)
    """
    # TODO if project num isn't set, we need a token to browse it
    if not session.project_num:
        return False

    # for current project, get all app results from BaseSpace        
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version, session.app_session_num, user_row.access_token)        
    proj = bs_api.getProjectById(session.project_num)    
    # only display first 10 AppResults
#    app_results = proj.getAppResults(bs_api, myQp={'Limit':10})
    app_results = proj.getAppResults(bs_api)
    
    # now build html list
    r=['<ul class="jqueryFileTree" style="display: none;">']
    #r.append('<li class="directory"><a href="#" rel="' + proj.Name + '/">' + proj.Name + '</a></li>')
    for result in app_results:
       r.append('<li class="directory collapsed"><a href="#" rel="' + proj.Name + '/' + result.Name + '/">' + result.Name + '</a></li>')
       bs_files = result.getFiles(bs_api, myQp={'Extensions':'bam', 'Limit':250})
       # TODO adjust file extensions
       for f in bs_files:
           r.append('<li class="file ext_txt"><a href="confirm_analysis_inputs?file_num=' + f.Id + '&app_result_num=' + result.Id + '" rel="' + proj.Name + '/' + result.Name + '/' + f.Name + '">' + f.Name + '</a></li>')

    r.append('</ul>')
    return ''.join(r)
    

# for user authentication
def user(): return dict(form=auth())
