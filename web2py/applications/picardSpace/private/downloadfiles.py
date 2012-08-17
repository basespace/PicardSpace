import time
while True:
    for row in db(db.download_queue.status=='pending').select():

        als_file = AnalysisInputFile(row.bs_file_id)
        if als_file.download_and_analyze():
            row.update_record(status='complete')
        else:
            row.update_record(status='failed')
        db.commit()
    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -N -R applications/picardSpace/private/downloadfiles.py
