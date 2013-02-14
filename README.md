PicardSpace
===========

A website that runs Picard tools for BaseSpace.


Setup
=====
1. Download and unzip web2py for linux (download Current version, Source Code).

        wget http://www.web2py.com/examples/static/web2py_src.zip
        unzip web2py_src.zip

2. Clone this PicardSpace repository into the web2py applications directory.

        cd web2py/applications
        git clone https://github.com/basespace/PicardSpace.git

3. Install redis and python-rq

        sudo apt-get install redis-server
        sudo pip install rq

4. Start web2py, first navigating to the main 'web2py' directory. A web browser should launch with address localhost:8000).

        cd ..
        python web2py.py

5. Start the download and analysis queues:

        python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/web2py-rq.py

6. Register your new PicardSpace app on the BaseSpace dev portal (developer.basespace.illumina.com) with these settings:
App Launch Location: Projects
Home Page: localhost:8000/PicardSpace
Redirect URI: localhost:8000/PicardSpace

7. Go to BaseSpace.com and launch your new app from any Project that contains an AppResult with a BAM file.


Production Deployment
============
1. Write error tickets to the db instead of the file system. To accomplish this, create a file named applications/PicardSpace/private/ticket_storage.txt that contains information about your database, such as:
sqlite://storage.sqlite

Also run this script in the background, which will transfer tickets from the local file system to the db every 5 minutes:
        python web2py.py -S PicardSpace -M -R scripts/tickets2db.py &

(for details visit: http://web2py.com/book/default/chapter/13#Collecting-tickets)

2. Purge web session data every 1 hour, since this can pile up over time.
Due to a bug in web2py v2.1.2, this command current works only with v2.3.2.
        python web2py.py -S PicardSpace -M -R scripts/sessions2trash.py -A -x 3600 -f -v &


