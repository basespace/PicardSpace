import time
while True:
    for row in db(db.analysis_queue.status=='pending').select():

        als = Analysis(row.bs_file_id)
        fb = als.run_analysis_and_writeback()
        row.update_record(status=fb.status)
        row.update_record(message=fb.message)
        #if als.run_analysis_and_writeback():
        #    row.update_record(status='complete')
        #else:
        #    row.update_record(status='failed')
        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/analyzefiles.py
