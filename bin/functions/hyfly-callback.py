import sys
import redis
from redis_functions import init, retrieve
import logging



def run():
    client = init()

    if client is None:
        log.error("Redis not initialised")
        return

    msg = ""

    try:
        status, status_updated, x = retrieve(client, 'system_status', freshness=None)
        counter, counter_updated, x = retrieve(client, 'counter', freshness=None)
        samples, samples_updated, x = retrieve(client, 'samples_pending_upload', freshness=None)

        if status is not None:
            msg += f"status: {status}"
        if counter is not None:
            msg += f" (i={counter})\n"
        if samples is not None:
            msg += f"{samples} pending"
        log.info(msg)

    except Exception as err:
        log.info(err)
        log.info("Status unavailable")


if __name__ == '__main__':
    # set up logger
    myFormat = '%(message)s'
    formatter = logging.Formatter(myFormat)
    logging.basicConfig(level='INFO', format=myFormat, stream=sys.stdout)
    log = logging.getLogger('hyfly-callback')
    log.setLevel('INFO')

    run()
