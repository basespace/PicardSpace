from redis import Redis
from rq import Queue

# set up Queue with connection Redis
app = db(db.app_data.id > 0).select().first()

redis = Redis(host=app.redis_host, port=int(app.redis_port))

q = Queue(connection=redis)
current.q = q
