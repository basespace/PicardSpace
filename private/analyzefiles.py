import time
from picardSpace import AnalysisInputFile, AppResult

while True:
    for row in db(db.analysis_queue.status=='pending').select():

        # get queued app result from db
        # note: assuming we're analyzing a single file per app result, for now
        f_row = db(db.bs_file.id==row.bs_file_id).select().first()
        ar_row = db(db.app_result.input_file_id==f_row.id).select().first()

        input_file = AnalysisInputFile(
            #app_result_id=ar_row.id,
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
            app_result_num=ar_row.app_result_num,
            status=ar_row.status)
            
        # run analysis and writeback results to BaseSpace
        try:
            fb = app_result.run_analysis_and_writeback(input_file)
            status = fb.status
            message = fb.message
        except Exception as e:
            # print error msg, update AppResult in db
            print "Error: {0}".format(str(e))
            status = 'error'
            message = str(e)
            row.update_record(status='error')
            ar_row.update_record(status='error', message=str(e))           
        # update analysis queue with analysis feedback
        row.update_record(status=status)
        row.update_record(message=message)

        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/analyzefiles.py
