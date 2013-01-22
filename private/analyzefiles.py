import time
from picardSpace import AnalysisInputFile, AppResult

while True:
    for row in db(db.analysis_queue.status=='pending').select():

        # get queued app result from db
        f_row = db(db.input_file.id==row.input_file_id).select().first()
        ar_row = db(db.output_app_result.input_file_id==f_row.id).select().first()
        ssn_row = db(db.app_session.id==ar_row.app_session_id).select().first()

        input_file = AnalysisInputFile(
            app_result_id=f_row.app_result_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        # create AppResult object to analyze downloaded File
        app_result = AppResult(
            app_result_id=ar_row.id,
            app_session_id=ar_row.app_session_id,
            project_num=ar_row.project_num,
            app_result_name=ar_row.app_result_name,
            app_result_num=ar_row.app_result_num)        
            
        # run analysis and writeback results to BaseSpace                        
        message = 'None'
        try:                        
            app_result.run_analysis_and_writeback(input_file) 
                                               
        except Exception as e:                                
            message = str(e)
            if e.message:
                message = message + " - " + e.message
            
            # append error message to existing app session status message (to keep context); print it
            message = app_result.status_message() + "; " + message                    
            print "Error: {0}".format(message)

            # update AppSession status in db and BaseSpace            
            try:            
                app_result.update_status('aborted', message, 'aborted')
            except Exception as e:
                # this error message will only print, not in db -- we tried! (user won't see it)
                print "Error updating AppSession status: {0} - {1}".format(str(e), e.message)                                                                                    
        
        # update analysis queue with analysis feedback
        row.update_record(status='complete')
        row.update_record(message=message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/analyzefiles.py
