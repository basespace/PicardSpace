# -*- coding: utf-8 -*-

import os.path
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import re
from picardSpace import File, AnalysisInputFile, readable_bytes, get_auth_code_util, get_access_token_util, download_bs_file
import shutil

# Auth notes:
# 1. All '@auth.requires_login' decorators redirect to login() if a user isn't logged in when the method is called (and _next=controller_method)
# 2. Once a user is logged into picardSpace, they can use their existing tokens to view the results -- even if they log out of BaseSpace -- because tokens are good regardless of BaseSpace login


def clear_session_vars():
    """
    Clear all session variables
    """
    session.app_session_num = None         # contains app sesssion num that user launched with from BaseSpace
    #session.login_scope = None             # scope for OAuth2 during login    
    session.oauth_return_url = None        # the url to return to when oauth is complete 
    session.in_login = False               # flag to handle_redirect_uri() to determine if in login or non-login oauth
    #session.token = None                   # holds access token from login oauth for recording in db after login (since getting project scope during login)


def handle_redirect_uri():
    """
    """    
    # handle api errors
    if (request.get_vars.error):
        err_msg = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(err_msg=err_msg)                    
        
    # handle case: just launched from BaseSpace 
    if (request.get_vars.appsessionuri):
        
        # clear all session variables
        clear_session_vars()
        
        # record app session number
        appsessionuri = request.get_vars.appsessionuri
        session.app_session_num = os.path.basename(appsessionuri)
    
        # get app session num from BaseSpace
        app = db(db.app_data.id > 0).select().first()
        try:
            bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,session.app_session_num)
            app_ssn = bs_api.getAppSession()     
        except Exception as e:
            return dict(err_msg=str(e))            
        
        # get the project num and access string of pre-selected Project
        ssn_ref = app_ssn.References[0]
        if (ssn_ref.Type != 'Project'):
            return dict(err_msg="Error - unrecognized reference type " + ssn_ref.Type + ". ")
        else:            
            ref_content = ssn_ref.Content
            project_num = ref_content.Id
            #session.login_scope = ref_content.getAccessStr(scope='read')
            
            # add ability to create project for writeback if needed
            #session.login_scope += ', create projects'                                
            
            # create app_session in db
            app_session_id = db.app_session.insert(app_session_num=session.app_session_num,
                project_num=project_num,
                date_created=app_ssn.DateCreated,
                status="newly created",
                message="newly launched App Session - no analysis performed yet")
            
            # log user into PicardSpace (user should already be logged into BaseSpace)            
            session.oauth_return_url = URL('user_now_logged_in')            
            redirect( URL('user', args=['login']) )
                                                                                                                                                                                                                                                                                                                                                                                              

    # handle OAuth2 response - exchange authorization code for auth token
    if (request.get_vars.code):
        
        # complete login, if login is in progress
        if session.in_login:
            #redirect( URL('user', args=['login'], vars=dict(code=request.get_vars.code, next=URL('user_now_logged_in'))))
            redirect( URL('user', args=['login'], vars=dict(code=request.get_vars.code)))

        # ensure user is logged in
        if not session.auth:
            return dict(err_msg="Error - user isn't logged in but should be")

        # non-login oauth2                        
        try:
            access_token = get_access_token_util(request.get_vars.code)
        except Exception as e:
            return dict(err_msg=str(e))

        # ensure the current app user is the same as the current BaseSpace user        
        user_row = db(db.auth_user.id==auth.user_id).select().first()
        cur_user_id = user_row.username
        app = db(db.app_data.id > 0).select().first()
        try:
            bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, session.app_session_num, access_token)
            bs_user = bs_api.getUserById('current')
        except Exception as e:
            return dict(err_msg=str(e))

        if (bs_user.Id != cur_user_id):
            return dict(err_msg="Error - mismatch between PicardSpace user id of " + str(cur_user_id) + " and current BaseSpace user id of " + str(bs_user.Id) + ". Please re-login to PicardSpace.")
                               
        # update user's access token in user table
        user_row.update_record(access_token=access_token)
        db.commit()
            
        # go to url specified by original call to get token
        redirect(session.oauth_return_url)            

    # shouldn't reach this point - redirect to index page
    redirect(URL('index'))     
                                            

def index():
    """
    Method for user reaching PicardScape outside of launch from BaseSpace -- offer login    
    """
    response.title = "PicardSpace"
    response.subtitle = "Home Page"

    # clear existing session vars 
    clear_session_vars()
    
    main_msg = 'Welcome to PicardSpace'
    scnd_msg = ''
    err_msg  = ''
           
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(URL('view_results'))       
        
    # construct login_url for login link, e.g.:
    # http://localhost:8000/PicardSpace/default/user/login?_next=/PicardSpace/default/user_now_logged_in'
    if (request.is_local):        
        login_url = URL('user', args=['login'], scheme=True, host=True, port=8000)  # vars=dict(_next=URL('user_now_logged_in')), 
    else:
        login_url = URL('user', args=['login'], scheme=True, host=True)
                                    
    return dict(main_msg=main_msg, scnd_msg=scnd_msg, err_msg=err_msg, login_url=login_url)


@auth.requires_login()
def user_now_logged_in():
    """
    Just determined that the user is logged into picardSpace; if a project context was provided, have user choose inputs, otherwise view results
    """
    # determine if the user pre-selected a sample/app_result/project to analyze
    if (not session.app_session_num):
        redirect(URL('view_results'))
    else:            
        # an app session num was provided, update app session with user info
        ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
        ssn_row.update_record(user_id=auth.user_id)

        # if just logged into session, record access token (needed since web2py will only record token on very first login)        
        #if session.token:
        #    user_row = db(db.auth_user.id==auth.user_id).select().first()
        #    user_row.update_record(access_token=session.token)
        #    session.token = None
        
        # start oauth to get browse access to launch Project and to create new Projects for writeback
        session.oauth_return_url = URL('choose_analysis_app_result', vars=dict(ar_offset=0, ar_limit=5))
        redirect(URL('get_auth_code', vars=dict(scope='create projects, browse project ' + str(ssn_row.project_num))))
        #redirect(URL('choose_analysis_app_result', vars=dict(ar_offset=0, ar_limit=5)))


@auth.requires_login()
def choose_analysis_app_result():
    """
    Offers the user choice of AppResult to analyze
    """
    ar_offset = 0
    const_ar_limit = 5
    ar_limit = const_ar_limit
    if request.vars.ar_offset:
        ar_offset=int(request.vars.ar_offset)
    if request.vars.ar_limit:
        ar_limit=int(request.vars.ar_limit)    

    # record offset and limit for 'back' link    
    ar_back = URL('choose_analysis_app_result', vars=dict(ar_offset=ar_offset, ar_limit=ar_limit))                    

    # get name of project from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
        proj = bs_api.getProjectById(ssn_row.project_num)
    except Exception as e:
        return dict(project_name="", ar_info="", ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", ar_back=ar_back, ar_offset=ar_offset, ar_limit=ar_limit, err_msg=str(e))        
    project_name = proj.Name    

    # get App Results for current Project, limited by limit and offset for performance
    ar_info = []    
    try:      
        # app_result list is in condensed API form - no References, Genome -- get these below                        
        #app_results = proj.getAppResults(bs_api, myQp={'Limit':ar_limit,'Offset':ar_offset})
        app_results = proj.getAppResults(bs_api, myQp={'Limit':1024})
        ar_tot = len(app_results)

        # don't allow indexing off end of app_results list
        ar_end = ar_offset+ar_limit        
        if ar_end > ar_tot:
            ar_end = ar_tot                
                                        
        for n in range(ar_offset,ar_end):        
            ar_short = app_results[n]
            
            # get full-form app_result from API to get Sample name (from relationship to AppResult)            
            ar = bs_api.getAppResultById(ar_short.Id)
            
            # get Samples - this method calls API once for each Sample
            samples = ar.getReferencedSamples(bs_api)

            # build string of Sample names for display            
            samples_names = []
            for s in samples:
                samples_names.append(s.Name)
          
            ar_info.append( { "app_result_name" : ar.Name + " - " + ', '.join(samples_names),    # + ", " + ar.DateCreated,
                              "app_result_num" : ar.Id } )                                                  
    except Exception as e:
        return dict(project_name=project_name, ar_info="", ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", ar_back=ar_back, ar_offset=ar_offset, ar_limit=ar_limit, err_msg=str(e))                                                                                                                                                                                 
    
    # calculate next and prev start/end                                                                                                                                        
    next_offset = ar_end
    next_limit = const_ar_limit    
    prev_offset = ar_offset - const_ar_limit
    prev_limit = const_ar_limit                                                                    
    if next_offset > ar_tot:
        next_offset = ar_tot    
    if prev_offset < 0:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        prev_offset = 0
                                                                                                                                                                                                                
    return dict(project_name=project_name, ar_info=ar_info, ar_start=ar_offset+1, ar_end=ar_end, ar_tot=ar_tot, next_offset=next_offset, next_limit=next_limit, prev_offset=prev_offset, prev_limit=prev_limit, ar_back=ar_back, ar_offset=ar_offset, ar_limit=ar_limit, err_msg="")


@auth.requires_login()
def choose_analysis_file():
    """
    Offers the user choice of file to analyze
    """
    # get required inputs app result selection and back link
    if ('ar_num' not in request.vars or
        'ar_back' not in request.vars):
        return dict(app_result_name="", file_info="", file_back="", ar_num="", ar_back="", err_msg="We have a problem - expected AppResult and back link but didn't receive them.")                 
    
    ar_num = request.vars['ar_num']                      
    ar_back = request.vars['ar_back']                    
    
    # create 'back' link    
    file_back = URL('choose_analysis_file', vars=dict(ar_num=ar_num, ar_back=ar_back))
                  
    # get list of BAM files for this AppResult from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)
        app_result = bs_api.getAppResultById(ar_num)
        bs_files = app_result.getFiles(bs_api, myQp={'Extensions':'bam', 'Limit':100})
    except Exception as e:
        return dict(app_result_name="", file_info="", file_back=file_back, ar_num=ar_num, ar_back=ar_back, err_msg=str(e))     
    
    # get Sample name from relationship to AppResult for display
    samples = app_result.getReferencedSamples(bs_api)

    # build string of Sample names for display            
    samples_names = []
    for s in samples:
        samples_names.append(s.Name)                
                
    # construct display name for each BAM file   
    file_info = []    
    for f in bs_files:      
        
        # don't allow analysis of files > 100 MB
        large_file = ""
        if (f.Size > 100000000):     
            large_file = "large_file"
            
        file_info.append( { "file_name" : f.Name + " (" + readable_bytes(f.Size) + ")",
                            "file_num" : f.Id,
                            #"app_result_num" : app_result.Id,
                            "large_file" : large_file } )                      
    
    app_result_name=app_result.Name + " - " + ', '.join(samples_names)
    
    return dict(app_result_name=app_result_name, file_info=file_info, file_back=file_back, ar_num=ar_num, ar_back=ar_back, err_msg="")


@auth.requires_login()
#def choose_writeback_project():
def confirm_analysis_inputs():
    """
    Presents final confirmation to user before launching analysis.
    Offers user form to name analysis (app result name currently).
    Checks that user owns Project that contains input file; if not, uses 'PicardSpace Result' Project, which will be created if it doesn't already exist.
    """
    # get file_num and app_result_num that user selected    
    if ('file_num' not in request.vars or
        'ar_num' not in request.vars or
        'file_back' not in request.vars):
        return dict(sample_name="", file_name="", project_name="", writeback_msg="", ar_num="", file_num="", file_back="", err_msg="We have a problem - expected File and AppResult info but didn't receive it")
    
    file_num = request.vars['file_num']
    ar_num = request.vars['ar_num']
    file_back = request.vars['file_back']


    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, session.app_session_num, user_row.access_token)        
        launch_project = bs_api.getProjectById(ssn_row.project_num)
        input_file = bs_api.getFileById(file_num)
        app_ssn = bs_api.getAppSession(session.app_session_num)

        app_result = bs_api.getAppResultById(ar_num)
        samples_ids = app_result.getReferencedSamplesIds()    
    except Exception as e:
        return dict(sample_name="", file_name="", project_name="", writeback_msg="", ar_num=ar_num, file_num=file_num, file_back=file_back, err_msg=str(e))        
    
    # get sample num and name from AppResult, if present; only recognizing single sample per app result for now
    sample_name = "unknown"
    if samples_ids:
        sample_num = samples_ids[0]
        try:
            sample = bs_api.getSampleById(sample_num)
        except Exception as e:  
            return dict(sample_name="", file_name="", project_name="", writeback_msg="", ar_num=ar_num, file_num=file_num, file_back=file_back, err_msg=str(e))        
             
        sample_name = sample.Name               

    # determine if user owns launch project, if not use 'PicardSpace Results' - won't create new project until after user confirms analysis
    if user_row.username == launch_project.UserOwnedBy.Id:
        # user is owner - assume they want to write back to source project
        try:
            project = bs_api.getProjectById(ssn_row.project_num)
        except Exception as e:          
            return dict(sample_name="", file_name="", project_name="", writeback_msg="", ar_num=ar_num, file_num=file_num, file_back=file_back, err_msg=str(e))        
        proj_name = project.Name
    else:
        proj_name = 'PicardSpace Results'

    # add writeback message if writing to PicardSpace Results project
    writeback_msg = ""
    if project.Name == 'PicardSpace Results':
        writeback_msg = "Since you are not the owner of the Project that contains the BAM file you selected, you can not save files in that Project. Instead, your output files will be saved in a BaseSpace Project that you own named 'PicardSpace Results'."
            
    return dict(sample_name=str(sample_name), file_name=str(input_file.Name), project_name=proj_name, writeback_msg=writeback_msg, ar_num=ar_num, file_num=file_num, file_back=file_back, err_msg="")        


@auth.requires_login()
def create_writeback_project():
    """
    Accepts app result name for new analysis and begins oauth process to start analysis
    """
    if ('ar_name' not in request.vars or
        'ar_num' not in request.vars or
        'file_num' not in request.vars):        
        return dict(err_msg="We have a problem - expected query variables but didn't receive them")
    
    ar_name = request.vars['ar_name']
    ar_num = request.vars['ar_num']
    file_num = request.vars['file_num']
    
    # get session id and current user id from db
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()                    
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, ssn_row.app_session_num, user_row.access_token)
        launch_project = bs_api.getProjectById(ssn_row.project_num)
    except Exception as e:
        return dict(err_msg=str(e))
    
    # if the user doesn't own the Project they launched with - create 'PicardSpace Results' Project or use it if it already exists    
    if user_row.username == launch_project.UserOwnedBy.Id:  
        wb_proj_num = ssn_row.project_num
    else:
        try:
            wb_proj = bs_api.createProject('PicardSpace Results')    
        except Exception as e:
            return dict(err_msg=str(e))
        wb_proj_num = wb_proj.Id

    # start oauth to get write project access, then start analysis
    session.oauth_return_url = URL('start_analysis', vars=dict(ar_name=ar_name, ar_num=ar_num, file_num=file_num, wb_proj_num=wb_proj_num))
    redirect(URL('get_auth_code', vars=dict(scope='write project ' + str(wb_proj_num))))    


@auth.requires_login()
def get_auth_code():
    """
    Begin Oauth process to get write access to writeback project
    """         
    if ('scope' not in request.vars):
        return dict(err_msg="We have a problem - expected scope but didn't receive it")
    scope = request.vars['scope']
    
    try:
        get_auth_code_util(scope)
    except Exception as e:
        return dict(err_msg=str(e))            


@auth.requires_login()
def start_analysis():
    """
    Create an app result in BaseSpace and the local db, then queue the input BAM file for download from BaseSpace
    """
    if ('ar_name' not in request.vars or
        'wb_proj_num' not in request.vars or
        'ar_num' not in request.vars or
        'file_num' not in request.vars):        
        return dict(err_msg="We have a problem - expected query variables but didn't receive them")
    
    ar_name = request.vars['ar_name']
    wb_proj_num = request.vars['wb_proj_num']
    ar_num = request.vars['ar_num']
    file_num = request.vars['file_num']
    
        
    # get input app result and sample objs from Basespace
    app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()                    
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, app_ssn_row.app_session_num, user_row.access_token)            
        input_app_result = bs_api.getAppResultById(ar_num)
        samples_ids = input_app_result.getReferencedSamplesIds()
    except Exception as e:
        return dict(err_msg=str(e))
    
    # get Samples referenced from AppResult - only recognizing single sample per app result for now
    sample_num = None
    sample = None
    if samples_ids:
        sample_num = samples_ids[0]
        try:
            sample = bs_api.getSampleById(sample_num)
        except Exception as e:
            return dict(err_msg=str(e))
            
    # add new AppResult to BaseSpace
    try:
        wb_proj = bs_api.getProjectById(wb_proj_num)    
        input_file = bs_api.getFileById(file_num)
        output_app_result = wb_proj.createAppResult(bs_api, ar_name, "PicardSpace AppResult", appSessionId=app_ssn_row.app_session_num, samples=[ sample ] )
    except Exception as e:
        return dict(err_msg=str(e))
    
    # add input AppResult to db
    input_app_result_id = db.input_app_result.insert(
        project_num=app_ssn_row.project_num,
        app_result_name=input_app_result.Name,
        app_result_num=ar_num,
        sample_num=sample_num)
    db.commit()
    
    # add input BAM file to db
    input_file_id = db.input_file.insert(
        app_result_id=input_app_result_id,
        file_num=file_num, 
        file_name=input_file.Name)
    db.commit()                    
                                                            
    # add new output AppResult to db            
    db.output_app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=wb_proj_num,
        app_result_name= ar_name,
        app_result_num=output_app_result.Id,
        sample_num=sample_num,        
        input_file_id=input_file_id)             
    db.commit()

    # add BAM File to download queue
    q.enqueue_call(func=download_bs_file, 
                   args=(input_file_id,),
                   timeout=86400) # seconds
    
    # update AppSession status
    app_ssn_row.update_record(status="beginning analysis", message="input file added to download queue")
    db.commit()    
            
    # clear session vars - everything should be in db
    clear_session_vars()

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis Has Started!')))    


@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """        
    # if arriving from just-launched analysis, display msg 'just launched'
    app_ssns = []
    message = ""
    if request.get_vars.message:
        message = request.get_vars.message    
        
    # handle pagination vars
    ar_offset = 0
    const_ar_limit = 5
    ar_limit = const_ar_limit
    if request.vars.ar_offset:
        ar_offset=int(request.vars.ar_offset)
    if request.vars.ar_limit:
        ar_limit=int(request.vars.ar_limit)    

    # record offset and limit for 'back' link    
    ar_back = URL('view_results', vars=dict(ar_offset=ar_offset, ar_limit=ar_limit))            
    
    # get BaseSpace API
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
    except Exception as e:
        return dict(message=message, app_ssns=app_ssns, ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", ar_back="", err_msg=str(e))
    
    # get app sessions for the current user, sorted by date created, limited to offset and limit    
    ssn_rows = db(db.app_session.user_id==auth.user_id).select(limitby=(ar_offset, ar_offset+ar_limit), orderby=~db.app_session.date_created)

    # get total number of app sessions
    ar_tot = db(db.app_session.user_id==auth.user_id).count()            
    
    # don't allow indexing off end of app_results list
    ar_end = ar_offset+ar_limit        
    if ar_end > ar_tot:
        ar_end = ar_tot                                                    
    
    for ssn_row in ssn_rows:
        # handling only one app result per app session
        rslt_row = db(db.output_app_result.app_session_id==ssn_row.id).select().first()
        # get project name for each AppResult    
        if rslt_row:
            try:
                proj = bs_api.getProjectById(rslt_row.project_num)
            except Exception as e:                 
                return dict(message=message, app_ssns=app_ssns, ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", ar_back="", err_msg=str(e))
                                

            app_ssns.append( { 'app_result_name':rslt_row.app_result_name, 'project_name':proj.Name, 'status':ssn_row.status, 'app_session_id':ssn_row.id, 'notes':ssn_row.message, 'date_created':ssn_row.date_created } )
        else:                 
            app_ssns.append( { 'app_result_name':'none', 'project_name':'none', 'status':ssn_row.status, 'app_session_id':ssn_row.id, 'notes':ssn_row.message, 'date_created':ssn_row.date_created } )
                
    # calculate next and prev start/end                                                                                                                                        
    next_offset = ar_end
    next_limit = const_ar_limit    
    prev_offset = ar_offset - const_ar_limit
    prev_limit = const_ar_limit                                                                    
    if next_offset > ar_tot:
        next_offset = ar_tot    
    if prev_offset < 0:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        prev_offset = 0
                
    return dict(message=message, app_ssns=app_ssns, ar_start=ar_offset+1, ar_end=ar_end, ar_tot=ar_tot, next_offset=next_offset, next_limit=next_limit, prev_offset=prev_offset, prev_limit=prev_limit, ar_back=ar_back, err_msg="")

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display picard's output from CollectAlignmentMetrics
    """
    app_session_id = request.get_vars.app_session_id
    
    # get 'back' url of view results page
    if (request.vars['ar_back']):
        ar_back=request.vars['ar_back']
    else:
        ar_back=URL('view_results')
    
    # set var defaults
    hdr = ""
    aln_tbl = []
    tps_aln_tbl = [["data not available"]]
    
    # get AppResult from db
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    output_ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    input_file_row = db(db.input_file.id==output_ar_row.input_file_id).select().first()
    input_ar_row = db(db.input_app_result.id==input_file_row.app_result_id).select().first()
    app = db(db.app_data.id > 0).select().first()    
                
    # get Sample and Project from BaseSpace
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, ssn_row.app_session_num, user_row.access_token)        
        sample = bs_api.getSampleById(output_ar_row.sample_num)        
        output_project = bs_api.getProjectById(output_ar_row.project_num)
        input_project = bs_api.getProjectById(input_ar_row.project_num)
    except Exception as e:    
        return(dict(aln_tbl=tps_aln_tbl, 
            hdr=hdr,
            sample_name="", 
            sample_num="",
            input_file_name="", 
            input_project_name="", 
            input_app_result_name="", 
            output_app_result_name="", 
            output_project_name="",
            ar_back=ar_back, 
            err_msg=str(e)))

    # get output file info from db    
    f_rows = db(db.output_file.app_result_id==output_ar_row.id).select()
    f_row = None
    for row in f_rows:
        # find file with aln metrics extension
        m = re.search(current.aln_metrics_ext + "$", row.file_name)
        if m:
            f_row = row
            break

    if f_row:        
        # create file object
        f = File(app_result_id=f_row.app_result_id,
                file_name=f_row.file_name,
                local_path=None,
                file_num=f_row.file_num)
        
        # download file from BaseSpace
        local_dir=os.path.join(request.folder, "private", "downloads", "viewing", str(ssn_row.app_session_num))         
        try:
            local_path = f.download_file(f_row.file_num, local_dir, app_session_id)
        except Exception as e:
            return(dict(aln_tbl=tps_aln_tbl, 
                hdr=hdr, 
                sample_name=sample.Name, 
                sample_num=sample.Id,
                input_file_name=input_file_row.file_name, 
                input_project_name=input_project.Name, 
                input_app_result_name=input_ar_row.app_result_name,  
                output_app_result_name=output_ar_row.app_result_name, 
                output_project_name=output_project.Name,
                ar_back=ar_back, 
                err_msg=str(e)))
        
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
            
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(local_path))            
        except Exception as e:
            return(dict(aln_tbl=tps_aln_tbl, 
                hdr=hdr, 
                sample_name=sample.Name, 
                sample_num=sample.Id,
                input_file_name=input_file_row.file_name, 
                input_project_name=input_project.Name, 
                input_app_result_name=input_ar_row.app_result_name,  
                output_app_result_name=output_ar_row.app_result_name, 
                output_project_name=output_project.Name,
                ar_back=ar_back, 
                err_msg=str(e)))

    return(dict(aln_tbl=tps_aln_tbl, 
        hdr=hdr, 
        sample_name=sample.Name, 
        sample_num=sample.Id,
        input_file_name=input_file_row.file_name, 
        input_project_name=input_project.Name,        
        input_app_result_name=input_ar_row.app_result_name,  
        output_app_result_name=output_ar_row.app_result_name, 
        output_project_name=output_project.Name,
        ar_back=ar_back, 
        err_msg=""))
                

# for user authentication
def user(): return dict(form=auth())
