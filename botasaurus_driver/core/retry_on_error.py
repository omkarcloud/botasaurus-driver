from functools import wraps
from time import sleep
import traceback

def is_errors_instance(instances, error):
    for i in range(len(instances)):
        ins = instances[i]
        if isinstance(error, ins):
            return True, i
    return False, -1

ANY = 'any'
def retry_if_is_error(instances=ANY, retries=3, wait_time=None, raise_exception=True, on_failed_after_retry_exhausted=None,on_error=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tries = 0

            while tries < retries:
                tries += 1
                try:
                    created_result = func(*args, **kwargs)
                    return created_result
                except Exception as e:
                    if on_error:
                        on_error(e)

                    if instances != ANY:
                        errors_only_instances = list(map(lambda el: el[0] if isinstance(el, tuple) else el, instances)) if instances else []
                    if instances != ANY:
                        is_valid_error, index = is_errors_instance(errors_only_instances, e)

                        if not is_valid_error:
                            raise e
                        
                    if raise_exception:
                        traceback.print_exc()

                    if instances != ANY:
                        if instances and isinstance(instances[index], tuple):
                            instances[index][1]()

                    if tries == retries:
                        if on_failed_after_retry_exhausted:
                            on_failed_after_retry_exhausted(e)
                        if raise_exception:
                            raise e

                    print('Retrying')

                    if wait_time is not None:
                        sleep(wait_time)
        return wrapper
    return decorator
